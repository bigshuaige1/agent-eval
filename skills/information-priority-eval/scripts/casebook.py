#!/usr/bin/env python3
"""Store small human-priority evaluation cases and optionally share one as a GitHub Issue."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from urllib import error, request
from urllib.parse import urlsplit
from uuid import uuid4


STAGES = {"goal", "retrieval", "selection", "generation", "presentation", "unknown"}
SOURCES = {"user_feedback", "independent_review", "agent_hypothesis"}
STATUSES = {"covered", "partial", "missing", "contradicted", "unknown"}
ID_PATTERN = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}\Z")
RECEIPT_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,200}={0,2}\Z")
REPO_PATTERN = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")


def check(case):
    if not isinstance(case, dict) or case.get("schema_version") != 1:
        raise ValueError("case must be a version 1 JSON object")
    if not isinstance(case.get("id"), str) or not ID_PATTERN.fullmatch(case["id"]):
        raise ValueError("id must use letters, digits, underscore or hyphen")
    if not isinstance(case.get("goal"), str) or not case["goal"].strip():
        raise ValueError("goal is required")
    if case.get("review_scope") not in {"partial", "complete"}:
        raise ValueError("review_scope must be partial or complete")
    rows = case.get("requirements")
    if not isinstance(rows, list) or not rows:
        raise ValueError("requirements must be a nonempty list")
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("each requirement must be an object")
        if not isinstance(row.get("finding"), str) or not row["finding"].strip():
            raise ValueError("each requirement needs a finding")
        if row.get("source") not in SOURCES or row.get("status") not in STATUSES:
            raise ValueError("invalid requirement source or status")
        if row.get("importance") not in {"critical", "ordinary"}:
            raise ValueError("importance must be critical or ordinary")
        if row.get("stage") not in STAGES:
            raise ValueError("invalid failure stage")
    if case["review_scope"] == "complete" and any(
        row["source"] == "agent_hypothesis" or row["status"] == "unknown" for row in rows
    ):
        raise ValueError("complete reviews require independently labelled, resolved requirements")
    return case


def save(store, case):
    check(case)
    folder = store / "cases"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / (case["id"] + ".json")
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=folder, delete=False) as tmp:
        json.dump(case, tmp, ensure_ascii=False, indent=2)
        tmp.write("\n")
        temporary = Path(tmp.name)
    try:
        os.link(temporary, target)  # Atomic and refuses to replace an existing case.
    finally:
        temporary.unlink(missing_ok=True)
    return target


def load_case(store, case_id):
    if not ID_PATTERN.fullmatch(case_id):
        raise ValueError("invalid case id")
    return check(json.loads((store / "cases" / (case_id + ".json")).read_text(encoding="utf-8")))


def issue_body(case):
    lines = ["## Human priority feedback", "", f"Case: {case['id']}",
             f"Goal: {case['goal']}", f"Review scope: {case['review_scope']}", ""]
    for index, row in enumerate(case["requirements"], 1):
        lines += [f"### Requirement {index}", f"Finding: {row['finding']}",
                  f"Source: {row['source']}", f"Importance: {row['importance']}",
                  f"Outcome: {row['status']}", f"Stage: {row['stage']}"]
        if row.get("impact"):
            lines.append(f"Consequence: {row['impact']}")
        lines.append("")
    return "\n".join(lines)


def receipt_path(store, repo, case_id):
    namespace = hashlib.sha256(repo.lower().encode()).hexdigest()[:16]
    return store / "sent" / namespace / (case_id + ".json")


def claim_path(store, repo, case_id):
    return receipt_path(store, repo, case_id).with_suffix(".claim")


def policy_path(store, repo):
    namespace = hashlib.sha256(repo.lower().encode()).hexdigest()[:16]
    return store / "policies" / (namespace + ".json")


def policy_mode(store, repo):
    path = policy_path(store, repo)
    if not path.exists():
        return "manual"
    policy = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(policy, dict) or policy.get("repo") != repo or policy.get("mode") not in {"manual", "auto"}:
        raise ValueError("invalid upload policy; refusing to upload")
    return policy["mode"]


def set_policy(store, repo, mode):
    if mode not in {"manual", "auto"}:
        raise ValueError("invalid upload policy mode")
    path = policy_path(store, repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                     delete=False) as output:
        json.dump({"repo": repo, "mode": mode,
                   "updated_at": datetime.now(timezone.utc).isoformat()}, output)
        output.write("\n")
        temporary = Path(output.name)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def pending_cases(store, repo):
    sent = receipt_path(store, repo, "unused").parent
    return [load_case(store, path.stem) for path in sorted((store / "cases").glob("*.json"))
            if not (sent / path.name).exists() and
            not (sent / (path.stem + ".claim")).exists()]


def write_receipt(store, repo, case_id, url):
    receipt = receipt_path(store, repo, case_id)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=receipt.parent,
                                     delete=False) as output:
        json.dump({"repo": repo, "case_id": case_id, "issue_url": url,
                   "submitted_at": datetime.now(timezone.utc).isoformat()}, output)
        output.write("\n")
        temporary = Path(output.name)
    try:
        os.link(temporary, receipt)
    finally:
        temporary.unlink(missing_ok=True)


def github_token():
    token = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")
    if token:
        return token
    if shutil.which("gh"):
        result = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True,
                                timeout=10, check=False)
        return result.stdout.strip() if result.returncode == 0 else None
    return None


def intake_endpoint(value):
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or
            parsed.query or parsed.fragment or parsed.path.rstrip("/") != "/v1/cases"):
        raise ValueError("endpoint must be an HTTPS URL ending in /v1/cases")
    return value.rstrip("/")


def submit_to_intake(store, endpoint, case):
    claim = claim_path(store, endpoint, case["id"])
    claim.parent.mkdir(parents=True, exist_ok=True)
    with claim.open("x", encoding="utf-8") as output:
        output.write("Submission started; ask the intake maintainer to reconcile before retrying.\n")
    payload = json.dumps({"id": case["id"], "title": f"[priority-eval] {case['id']}",
                          "body": issue_body(case)}).encode()
    req = request.Request(endpoint, data=payload,
                          headers={"Content-Type": "application/json",
                                   "User-Agent": "information-priority-eval"}, method="POST")
    with request.urlopen(req, timeout=20) as response:
        receipt = json.load(response)["receipt"]
    if not isinstance(receipt, str) or not RECEIPT_PATTERN.fullmatch(receipt):
        raise ValueError("intake returned an invalid receipt; submission is unresolved")
    write_receipt(store, endpoint, case["id"], receipt)
    claim.unlink()
    print(f"Private intake receipt: {receipt}")


def submit_case(store, repo, case, token=None):
    token = token or github_token()
    if not token:
        raise ValueError("GH_TOKEN or GITHUB_TOKEN is required to publish")
    claim = claim_path(store, repo, case["id"])
    claim.parent.mkdir(parents=True, exist_ok=True)
    with claim.open("x", encoding="utf-8") as output:
        output.write("Submission started; inspect GitHub before retrying if no receipt appears.\n")
    body = issue_body(case)
    payload = json.dumps({"title": f"[priority-eval] {case['id']}", "body": body}).encode()
    req = request.Request(f"https://api.github.com/repos/{repo}/issues", data=payload,
                          headers={"Authorization": f"Bearer {token}",
                                   "Accept": "application/vnd.github+json",
                                   "Content-Type": "application/json",
                                   "User-Agent": "information-priority-eval"}, method="POST")
    with request.urlopen(req, timeout=20) as response:
        url = json.load(response)["html_url"]
    write_receipt(store, repo, case["id"], url)
    claim.unlink()
    print(url)


def review_and_sync(store, repo, selected=None, max_batch=10, endpoint=None):
    destination = endpoint or repo
    cases = pending_cases(store, destination)
    if selected is not None:
        cases = [case for case in cases if case["id"] == selected]
    cases = cases[:max_batch]
    if not cases:
        print("No pending cases.")
        claims = list(receipt_path(store, destination, "unused").parent.glob("*.claim"))
        if claims:
            print(f"Unresolved submissions: {len(claims)}. Reconcile with the destination, then use resolve.")
        return
    auto = policy_mode(store, destination) == "auto"
    if auto:
        print(f"Auto-upload enabled for this store and {destination}; pending: {len(cases)}.")
    else:
        for case in cases:
            print(issue_body(case))
        print(f"Pending: {len(cases)}. These summaries will be sent to {destination}.")
        if not sys.stdin.isatty():
            print("No interactive terminal and no auto-upload consent; nothing uploaded.")
            return
    token = None if endpoint else github_token()
    if not endpoint and not token:
        print("No GitHub login found; use GH_TOKEN/GITHUB_TOKEN or gh auth login.")
        return
    if not auto:
        choice = input(f"Enter = upload once; ALWAYS = auto-upload future cases to {destination} without review; other text = skip: ")
        if choice == "ALWAYS":
            set_policy(store, destination, "auto")
            auto = True
            print("Auto-upload enabled for this store and destination. Use policy --manual to revoke.")
        elif choice != "":
            print("Skipped; cases remain pending.")
            return
    for case in cases:
        if auto and policy_mode(store, destination) != "auto":
            print("Auto-upload revoked; remaining cases are pending.")
            break
        if endpoint:
            submit_to_intake(store, endpoint, case)
        else:
            submit_case(store, repo, case, token=token)


def report(store):
    files = sorted((store / "cases").glob("*.json"))
    cases = [check(json.loads(path.read_text(encoding="utf-8"))) for path in files]
    labelled = [row for case in cases for row in case["requirements"]
                if row["source"] != "agent_hypothesis"]
    complete = [case for case in cases if case["review_scope"] == "complete" and
                any(row["source"] != "agent_hypothesis" and row["importance"] == "critical"
                    for row in case["requirements"])]
    failures = sum(any(row["importance"] == "critical" and
                       row["status"] in {"missing", "partial", "contradicted"}
                       for row in case["requirements"]) for case in complete)
    print(f"Cases: {len(cases)}; independently labelled requirements: {len(labelled)}")
    print("Outcomes: " + ", ".join(f"{status}={sum(row['status'] == status for row in labelled)}"
                                  for status in sorted(STATUSES)))
    print(f"Critical omissions in complete reviews: {failures}/{len(complete)}" +
          (f" ({failures / len(complete):.1%})" if complete else " (rate unavailable)"))
    bad = [row for row in labelled if row["status"] in {"missing", "partial", "contradicted"}]
    print("Failure stages: " + ", ".join(f"{stage}={sum(row['stage'] == stage for row in bad)}"
                                       for stage in sorted(STAGES)))
    print("This describes recorded cases only; feedback-selected cases do not estimate a population rate.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("template")
    capture = sub.add_parser("capture")
    capture.add_argument("--store", type=Path, required=True)
    capture.add_argument("--goal", required=True)
    capture.add_argument("--finding", required=True)
    capture.add_argument("--impact", default="")
    capture.add_argument("--stage", choices=sorted(STAGES), default="unknown")
    capture.add_argument("--importance", choices=["critical", "ordinary"], default="ordinary")
    capture.add_argument("--status", choices=sorted(STATUSES), default="missing")
    capture.add_argument("--artifact", default="")
    capture.add_argument("--endpoint", default=os.getenv("AGENT_EVAL_ENDPOINT"))
    add = sub.add_parser("add")
    add.add_argument("--store", type=Path, required=True)
    add.add_argument("--input", type=Path, required=True)
    add.add_argument("--endpoint", default=os.getenv("AGENT_EVAL_ENDPOINT"))
    summary = sub.add_parser("report")
    summary.add_argument("--store", type=Path, required=True)
    for name in ("publish", "sync", "watch", "resolve", "policy"):
        command = sub.add_parser(name)
        command.add_argument("--store", type=Path, required=True)
        command.add_argument("--repo", help="explicit public GitHub Issues destination")
        command.add_argument("--endpoint", help="private HTTPS intake; selected unless --repo is explicit")
        if name in {"publish", "resolve"}:
            command.add_argument("--id", required=True)
        if name in {"sync", "watch"}:
            command.add_argument("--max-batch", type=int, default=10)
        if name == "watch":
            command.add_argument("--every-minutes", type=int, default=60,
                                 help="check interval in minutes (default: 60)")
        if name == "resolve":
            outcome = command.add_mutually_exclusive_group(required=True)
            outcome.add_argument("--issue-url")
            outcome.add_argument("--receipt")
            outcome.add_argument("--not-created", action="store_true")
        if name == "policy":
            command.add_argument("--manual", action="store_true",
                                 help="revoke auto-upload for this store and repository")
    args = parser.parse_args()

    if args.command == "template":
        print(json.dumps({"schema_version": 1, "id": "replace-with-case-id", "goal": "Task goal",
                          "review_scope": "complete", "artifact": "local reference, never published",
                          "requirements": [{"finding": "Independently identified requirement",
                                            "source": "independent_review", "importance": "critical",
                                            "status": "missing", "stage": "selection",
                                            "impact": "Consequence of omission"}]}, ensure_ascii=False, indent=2))
    elif args.command == "capture":
        endpoint = intake_endpoint(args.endpoint) if args.endpoint else None
        case = {"schema_version": 1, "id": "case-" + uuid4().hex[:12], "goal": args.goal,
                "review_scope": "partial", "artifact": args.artifact,
                "requirements": [{"finding": args.finding, "source": "user_feedback",
                                  "importance": args.importance, "status": args.status,
                                  "stage": args.stage, "impact": args.impact}]}
        print(save(args.store, case))
        if endpoint:
            review_and_sync(args.store, None, selected=case["id"], max_batch=1,
                            endpoint=endpoint)
    elif args.command == "add":
        endpoint = intake_endpoint(args.endpoint) if args.endpoint else None
        case = json.loads(args.input.read_text(encoding="utf-8"))
        print(save(args.store, case))
        if endpoint:
            review_and_sync(args.store, None, selected=case["id"], max_batch=1,
                            endpoint=endpoint)
    elif args.command == "report":
        report(args.store)
    elif args.command in {"publish", "sync", "watch", "resolve", "policy"}:
        chosen_endpoint = args.endpoint or (None if args.repo else os.getenv("AGENT_EVAL_ENDPOINT"))
        endpoint = intake_endpoint(chosen_endpoint) if chosen_endpoint else None
        if not endpoint and not args.repo:
            raise ValueError("configure AGENT_EVAL_ENDPOINT or explicitly pass --repo")
        destination = endpoint or args.repo
        if args.repo and (not REPO_PATTERN.fullmatch(args.repo) or ".." in args.repo):
            raise ValueError("repo must be OWNER/REPO")
        if args.command in {"publish", "resolve"} and not ID_PATTERN.fullmatch(args.id):
            raise ValueError("invalid case id")
        if args.command == "policy":
            if args.manual:
                set_policy(args.store, destination, "manual")
            print(f"Upload policy for {destination}: {policy_mode(args.store, destination)}")
            return
        if args.command == "resolve":
            claim = claim_path(args.store, destination, args.id)
            if not claim.exists():
                raise ValueError("no unresolved submission for this case")
            if args.receipt:
                if not endpoint or not RECEIPT_PATTERN.fullmatch(args.receipt):
                    raise ValueError("receipt requires a private endpoint and a valid value")
                write_receipt(args.store, destination, args.id, args.receipt)
                claim.unlink()
                print("Marked as sent.")
            elif args.issue_url:
                if endpoint:
                    raise ValueError("use --receipt for a private endpoint")
                expected = f"https://github.com/{args.repo}/issues/"
                if not args.issue_url.startswith(expected) or not args.issue_url[len(expected):].isdigit():
                    raise ValueError("issue-url must be an Issue in the selected repository")
                write_receipt(args.store, destination, args.id, args.issue_url)
                claim.unlink()
                print("Marked as sent.")
            else:
                claim.unlink()
                print("Requeued after external verification that no Issue was created.")
            return
        if args.command == "watch" and args.every_minutes < 1:
            raise ValueError("every-minutes must be at least 1")
        if args.command != "publish" and args.max_batch < 1:
            raise ValueError("max-batch must be at least 1")
        if args.command == "publish":
            if endpoint:
                review_and_sync(args.store, args.repo, selected=args.id, max_batch=1,
                                endpoint=endpoint)
            else:
                review_and_sync(args.store, args.repo, selected=args.id, max_batch=1)
        elif args.command == "sync":
            if endpoint:
                review_and_sync(args.store, args.repo, max_batch=args.max_batch,
                                endpoint=endpoint)
            else:
                review_and_sync(args.store, args.repo, max_batch=args.max_batch)
        else:
            if not sys.stdin.isatty() and policy_mode(args.store, destination) != "auto":
                raise ValueError("watch requires a terminal until auto-upload is enabled")
            print(f"Watching every {args.every_minutes} minutes; Ctrl-C stops it.")
            while True:
                if endpoint:
                    review_and_sync(args.store, args.repo, max_batch=args.max_batch,
                                    endpoint=endpoint)
                else:
                    review_and_sync(args.store, args.repo, max_batch=args.max_batch)
                time.sleep(args.every_minutes * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Stopped.", file=sys.stderr)
        sys.exit(130)
    except (ValueError, OSError, json.JSONDecodeError, error.HTTPError, KeyError,
            subprocess.SubprocessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
