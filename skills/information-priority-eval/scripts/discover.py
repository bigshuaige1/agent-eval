#!/usr/bin/env python3
"""Find possible user-priority corrections in local Codex records, without publishing."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile


SIGNAL = re.compile(
    r"你(?:漏|没提|忽略|遗漏|没关注|没有回答)|"
    r"(?:漏掉|遗漏|忽略)(?:了|的)?(?:关键|重点|要求|信息)|"
    r"(?:重点|关键)(?:不是|在于|是)|"
    r"(?:不需要|不对|不准确|不是这样|你应该|你需要|请不要|需要补充|要全面)|"
    r"(?:missed|omitted|overlooked|forgot) (?:the |a )?(?:point|requirement|constraint|detail)|"
    r"(?:not what I asked|missed the point|you forgot|you ignored|please don't)", re.I)
SECRET = re.compile(r"(?:sk-[A-Za-z0-9_-]{12,}|ghp_[A-Za-z0-9]{12,}|github_pat_[A-Za-z0-9_]{12,}|Bearer\s+\S+)")
CONTEXT_LIMIT = 800
MESSAGE_LIMIT = 1200


def direct_user_text(text):
    stripped = text.lstrip()
    return not (stripped.startswith(("<skill>", "<codex_internal_context", "```")) or
                re.match(r"\[\d+\]\s+(?:tool|assistant|user)\b", stripped) or
                stripped.startswith('{"command":') or stripped.startswith('{"cmd":'))


def candidates_from_text(text, source, locator, previous_user="", previous_assistant=""):
    if not isinstance(text, str):
        return
    for match in SIGNAL.finditer(text):
        start = max(0, min(match.start() - 300, len(text) - MESSAGE_LIMIT))
        snippet = text[start:start + MESSAGE_LIMIT]
        yield {"id": hashlib.sha256(text.encode()).hexdigest()[:16],
               "source": source, "locator": locator, "signal": match.group(0),
               "message": SECRET.sub("[REDACTED]", snippet),
               "previous_user": SECRET.sub("[REDACTED]", previous_user[-CONTEXT_LIMIT:]),
               "previous_assistant": SECRET.sub("[REDACTED]", previous_assistant[-CONTEXT_LIMIT:]),
               "status": "candidate_only"}
        break


def messages(path):
    with path.open(encoding="utf-8", errors="replace") as stream:
        for number, line in enumerate(stream, 1):
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if path.name == "history.jsonl":
                if isinstance(row.get("text"), str):
                    yield row["text"], number, "user"
            elif row.get("type") == "response_item":
                item = row.get("payload") or {}
                if item.get("role") in {"user", "assistant"}:
                    for part in item.get("content", []):
                        if part.get("type") in {"input_text", "output_text"} and isinstance(part.get("text"), str):
                            yield part["text"], number, item["role"]


def scan(paths, budget, limit, include_all_messages=False, include_context=False):
    found = {}
    archive = {}
    consumed = 0
    for path, source in paths:
        if not path.is_file() or path.is_symlink():
            continue
        size = path.stat().st_size
        if budget and size > budget - consumed:
            continue
        consumed += size
        if path.suffix == ".jsonl":
            records = messages(path)
        else:
            def lines():
                with path.open(encoding="utf-8", errors="replace") as stream:
                    for number, line in enumerate(stream, 1):
                        yield line, number, "context"
            records = lines()
        previous_user = previous_assistant = ""
        for text, number, role in records:
            if role == "assistant":
                if not text.lstrip().startswith('{"risk_level":'):
                    previous_assistant = text
                continue
            if role not in ({"user", "context"} if include_context else {"user"}) or not direct_user_text(text):
                continue
            locator = f"{path}:{number}"
            if include_all_messages and role == "user" and text.strip():
                digest = hashlib.sha256(text.encode()).hexdigest()[:16]
                entry = {"id": digest, "source": source, "locator": locator,
                         "message": SECRET.sub("[REDACTED]", text),
                         "previous_user": SECRET.sub("[REDACTED]", previous_user[-CONTEXT_LIMIT:]) if source == "codex_user_session" else "",
                         "previous_assistant": SECRET.sub("[REDACTED]", previous_assistant[-CONTEXT_LIMIT:]) if source == "codex_user_session" else ""}
                if digest not in archive or (entry["previous_assistant"] and
                                             not archive[digest]["previous_assistant"]):
                    archive[digest] = entry
            for item in candidates_from_text(text, source, locator,
                                             previous_user if source == "codex_user_session" else "",
                                             previous_assistant if source == "codex_user_session" else ""):
                if item["id"] not in found or (item["previous_assistant"] and
                                               not found[item["id"]]["previous_assistant"]):
                    found[item["id"]] = item
                if limit and len(found) >= limit:
                    return list(found.values()), list(archive.values()), consumed
            previous_user = text
    return list(found.values()), list(archive.values()), consumed


def write_jsonl(target, items):
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target.parent, delete=False) as out:
        for item in items:
            out.write(json.dumps(item, ensure_ascii=False) + "\n")
        temporary = Path(out.name)
    os.replace(temporary, target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--codex-home", type=Path, default=Path(os.getenv("CODEX_HOME", Path.home() / ".codex")))
    parser.add_argument("--path", type=Path, action="append", default=[],
                        help="additional JSONL path; Markdown needs --include-context-candidates")
    parser.add_argument("--max-mib", type=int, default=0, help="optional read limit; 0 scans all files")
    parser.add_argument("--max-candidates", type=int, default=0, help="optional result limit; 0 keeps all")
    parser.add_argument("--include-all-messages", action="store_true",
                        help="also save all user messages and their context locally")
    parser.add_argument("--include-context-candidates", action="store_true",
                        help="also search Memory and explicit Markdown paths as unverified context")
    args = parser.parse_args()
    if args.max_mib < 0 or args.max_candidates < 0:
        parser.error("limits cannot be negative")
    home = args.codex_home.expanduser()
    paths = [(home / "history.jsonl", "codex_user_history")]
    memories = home / "memories"
    if args.include_context_candidates and memories.is_dir():
        paths += [(path, "memory_context") for path in sorted(memories.rglob("*.md"))]
    for path in args.path:
        if path.is_dir():
            if args.include_context_candidates:
                paths += [(item, "additional_context") for item in sorted(path.rglob("*.md"))]
            paths += [(item, "additional_context") for item in sorted(path.rglob("*.jsonl"))]
        else:
            if path.suffix == ".jsonl" or args.include_context_candidates:
                paths.append((path, "additional_context"))
    sessions = home / "sessions"
    if sessions.is_dir():
        paths += [(path, "codex_user_session") for path in
                  sorted(sessions.rglob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)]
    items, archive, consumed = scan(paths, args.max_mib * 1024 * 1024,
                                    args.max_candidates, args.include_all_messages,
                                    args.include_context_candidates)
    args.store.mkdir(parents=True, exist_ok=True)
    target = args.store / "discovery.jsonl"
    write_jsonl(target, items)
    if args.include_all_messages:
        write_jsonl(args.store / "user_messages.jsonl", archive)
    print(f"Candidates: {len(items)}; user messages: {len(archive)}; scanned: {consumed} bytes; store: {args.store}")
    print("Discovery records are unverified and are never uploaded by casebook.py.")


if __name__ == "__main__":
    main()
