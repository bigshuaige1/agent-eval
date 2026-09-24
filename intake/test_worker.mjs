import assert from "node:assert/strict";
import worker from "./worker.mjs";

class Headers {
  constructor(values = {}) { this.values = values; }
  get(name) { return this.values[name] ?? null; }
}
class Request {
  constructor(url, options) {
    this.url = url;
    this.method = options.method;
    this.headers = new Headers(options.headers);
    this.body = options.body;
  }
  async text() { return this.body; }
}
class Response {
  constructor(body, options = {}) {
    this.body = body;
    this.status = options.status || 200;
    this.ok = this.status >= 200 && this.status < 300;
  }
  static json(value, options) { return new Response(JSON.stringify(value), options); }
  async json() { return JSON.parse(this.body); }
}
globalThis.Response = Response;

const body = "## Human priority feedback\n\nCase: case-1\nGoal: Choose a plan\n\nSource: user_feedback";
const item = { id: "case-1", title: "[priority-eval] case-1", body };
const env = { GITHUB_TOKEN: "test-only", RATE_LIMITER: { limit: async () => ({ success: true }) } };
let sent;
const originalFetch = globalThis.fetch;
globalThis.fetch = async (url, options) => {
  sent = { url, options };
  return Response.json({ node_id: "I_private_123" }, { status: 201 });
};
try {
  const req = new Request("https://intake.example/v1/cases", {
    method: "POST", headers: { "CF-Connecting-IP": "127.0.0.1" }, body: JSON.stringify(item),
  });
  const response = await worker.fetch(req, env);
  assert.equal(response.status, 201);
  assert.deepEqual(await response.json(), { receipt: "I_private_123" });
  assert.equal(sent.url, "https://api.github.com/repos/bigshuaige1/agent-eval-data/issues");
  assert.deepEqual(JSON.parse(sent.options.body), { title: item.title, body });

  const bad = new Request("https://intake.example/v1/cases", {
    method: "POST", body: JSON.stringify({ ...item, title: "other" }),
  });
  assert.equal((await worker.fetch(bad, env)).status, 400);
  assert.equal((await worker.fetch(new Request("https://intake.example/v1/cases", {
    method: "POST", body: JSON.stringify(item),
  }), { ...env, RATE_LIMITER: { limit: async () => ({ success: false }) } })).status, 429);
} finally {
  globalThis.fetch = originalFetch;
}
