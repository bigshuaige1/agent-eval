# Private intake deployment

`worker.mjs` accepts short case summaries at `POST /v1/cases` and creates Issues in the private `bigshuaige1/agent-eval-data` repository. It returns an opaque receipt. Contributors never receive the repository credential.

1. Create a fine-grained GitHub personal access token scoped only to `bigshuaige1/agent-eval-data` with **Issues: read and write**. Use an expiry and rotate it before expiry.
2. In a Cloudflare account, authenticate Wrangler, then from this directory run `npx wrangler secret put GITHUB_TOKEN`. Enter the token at Wrangler's hidden prompt; do not place it in a command, file, or chat.
3. Run `npx wrangler deploy`. The `RATE_LIMITER` binding in `wrangler.toml` allows at most 10 requests per minute per connecting IP. Verify the Worker URL and set contributors' `AGENT_EVAL_ENDPOINT` to `https://YOUR-WORKER.workers.dev/v1/cases`.
4. In the Cloudflare dashboard, restrict public access and add abuse controls appropriate for the contributor group before broad distribution. The bundled rate limit alone cannot prevent distributed spam or forged cases.

`worker.mjs` does not log request bodies. Its validation limits size and checks the collector's case format, but a public endpoint cannot prove that a submitted label came from a real user. Treat private Issues as untrusted until reviewed. Do not configure an unrestricted token or share the private repository's URL with contributors as an upload method.

The client only sends `id`, `title`, and a short formatted `body`. Discovery archives and local `artifact` references never enter the request. If a request times out after GitHub created the Issue, the client holds a local claim and does not retry automatically; the maintainer can reconcile it by case ID.
