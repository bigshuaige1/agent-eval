# Cloudflare HTTPS intake

`worker.mjs` receives short case summaries at `POST /v1/cases`, checks a contributor token, limits each token to 10 submissions per minute, and creates an Issue in the private `bigshuaige1/agent-eval-data` repository. It returns an opaque receipt. Discovery archives and local artifact paths are excluded by the client and rejected by the receiver.

The Worker is deployed as `agent-eval-intake` on `bigshuaige1-agent-eval.workers.dev`. Its route is enabled, but uploads remain unavailable until both production secrets below are configured and an external request test succeeds. A `GET /healthz` response only checks that the script runs; it does not prove that GitHub delivery works. PjLab's current proxy cannot complete TLS to this `workers.dev` hostname, so test from a contributor network before distributing the URL.

## Production secrets

- `GITHUB_TOKEN`: a **fine-grained** GitHub token restricted to `bigshuaige1/agent-eval-data` with `Issues: write`. Do not bind a broad classic `repo` token to the Worker.
- `UPLOAD_TOKEN_HASHES`: one SHA-256 hex digest per contributor token, separated by newlines or spaces. Give each contributor a distinct random token of at least 32 characters through a secure channel. Keep raw tokens in their secret managers, not in this repository.

Set these as Cloudflare Worker Secrets in the dashboard or with `wrangler secret put`. Do not put them in `wrangler.toml`, code, Git, shell history, or task logs. To calculate a digest without echoing the token:

```bash
python3 -c 'import getpass,hashlib; print(hashlib.sha256(getpass.getpass("Upload token: ").encode()).hexdigest())'
```

The API token used to deploy this Worker was pasted into a chat and should be rotated before further production use. R2 access keys are not used by this design and should also be rotated because they were exposed in the same message.

## Update and verify

The source of truth is `worker.mjs` and `wrangler.toml`. From `intake/`, deploy with Wrangler under an account identity allowed to edit this Worker. `wrangler.toml` declares the rate limiter binding. The Worker checks that both secrets and the binding exist before accepting a case.

After setting secrets, test from a network outside PjLab:

1. `GET https://agent-eval-intake.bigshuaige1-agent-eval.workers.dev/healthz` returns HTTP 200.
2. An unauthenticated `POST /v1/cases` returns HTTP 401.
3. A synthetic case sent with a valid contributor token returns HTTP 201 and a receipt; confirm the private Issue was created. Do not use a real conversation for this test.
4. Test that an extra `artifact` field and an oversized body are rejected, and that the case body in the private Issue contains only the intended short summary.

Then contributors set `AGENT_EVAL_ENDPOINT=https://agent-eval-intake.bigshuaige1-agent-eval.workers.dev/v1/cases` and `AGENT_EVAL_UPLOAD_TOKEN` through their environment or secret manager. The local casebook's Enter and `ALWAYS` choices still control upload consent. If a request times out, reconcile by case ID before retrying because the Issue might already exist.

Only case summaries are sent to Cloudflare and GitHub; they do leave PjLab. Do not add full local discovery archives or raw user-message files to this endpoint.
