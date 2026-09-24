#!/usr/bin/env python3
"""Small authenticated intake behind a TLS-terminating Kubernetes Ingress."""

from collections import deque
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import hmac
import json
import os
import re
import socket
from threading import Lock
import time
from urllib import error, request


GITHUB_ISSUES = "https://api.github.com/repos/bigshuaige1/agent-eval-data/issues"
CASE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}\Z")
RECEIPT = re.compile(r"[A-Za-z0-9_-]{1,200}={0,2}\Z")
TOKEN_HASH = re.compile(r"[0-9a-f]{64}\Z")
MAX_BYTES = 8192
RATE_LIMIT = 10
RATE_WINDOW = 60
_hits = {}
_lock = Lock()


def valid_case(item):
    if not isinstance(item, dict) or set(item) != {"id", "title", "body"}:
        return False
    case_id = item["id"]
    body = item["body"]
    return (isinstance(case_id, str) and bool(CASE_ID.fullmatch(case_id)) and
            item["title"] == f"[priority-eval] {case_id}" and
            isinstance(body, str) and len(body) <= 6000 and
            body.startswith(f"## Human priority feedback\n\nCase: {case_id}\n") and
            re.search(r"^Source: (user_feedback|independent_review)$", body, re.M) is not None)


def authorized(header, token_hashes):
    if not header or not header.startswith("Bearer "):
        return None
    token = header[7:]
    if len(token) < 32 or len(token) > 256:
        return None
    digest = hashlib.sha256(token.encode()).hexdigest()
    matched = False
    for value in token_hashes:
        matched |= hmac.compare_digest(digest, value)
    return digest if matched else None


def admitted(digest):
    now = time.monotonic()
    with _lock:
        queue = _hits.setdefault(digest, deque())
        while queue and queue[0] <= now - RATE_WINDOW:
            queue.popleft()
        if len(queue) >= RATE_LIMIT:
            return False
        queue.append(now)
    return True


def create_issue(item, github_token):
    payload = json.dumps({"title": item["title"], "body": item["body"]}).encode()
    req = request.Request(GITHUB_ISSUES, data=payload, method="POST", headers={
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "User-Agent": "agent-eval-intake",
    })
    with request.urlopen(req, timeout=20) as response:
        receipt = json.load(response).get("node_id")
    if not isinstance(receipt, str) or not RECEIPT.fullmatch(receipt):
        raise ValueError("GitHub returned no valid receipt")
    return receipt


class Handler(BaseHTTPRequestHandler):
    github_token = ""
    token_hashes = ()

    def respond(self, status, data):
        payload = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
        print(f"intake status={status}", flush=True)

    def log_message(self, *_):
        pass  # Do not log request paths, headers, or bodies.

    def do_GET(self):
        self.respond(200 if self.path == "/healthz" else 404,
                     {"status": "ok"} if self.path == "/healthz" else {"error": "not found"})

    def do_POST(self):
        self.connection.settimeout(10)
        if self.path != "/v1/cases":
            return self.respond(404, {"error": "not found"})
        digest = authorized(self.headers.get("Authorization"), self.token_hashes)
        if not digest:
            return self.respond(401, {"error": "unauthorized"})
        if not admitted(digest):
            return self.respond(429, {"error": "too many submissions"})
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            return self.respond(411, {"error": "Content-Length required"})
        if length < 1 or length > MAX_BYTES:
            return self.respond(413, {"error": "invalid body size"})
        if not self.headers.get("Content-Type", "").startswith("application/json"):
            return self.respond(415, {"error": "JSON required"})
        try:
            item = json.loads(self.rfile.read(length))
        except socket.timeout:
            return self.respond(408, {"error": "request timeout"})
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self.respond(400, {"error": "invalid JSON"})
        if not valid_case(item):
            return self.respond(400, {"error": "invalid case"})
        try:
            receipt = create_issue(item, self.github_token)
        except (error.HTTPError, error.URLError, TimeoutError, ValueError):
            return self.respond(502, {"error": "private repository unavailable"})
        return self.respond(201, {"receipt": receipt})


def main():
    github_token = os.getenv("GITHUB_TOKEN", "")
    token_hashes = tuple(os.getenv("UPLOAD_TOKEN_HASHES", "").split())
    if not github_token or not token_hashes or any(not TOKEN_HASH.fullmatch(x) for x in token_hashes):
        raise SystemExit("GITHUB_TOKEN and valid UPLOAD_TOKEN_HASHES are required")
    Handler.github_token = github_token
    Handler.token_hashes = token_hashes
    # ponytail: one serial server; add a bounded worker pool if uploads become frequent.
    HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()


if __name__ == "__main__":
    main()
