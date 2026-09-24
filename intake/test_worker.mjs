import assert from "node:assert/strict";
import { createHash, webcrypto } from "node:crypto";
import { test } from "node:test";
import worker from "./worker.mjs";

globalThis.crypto ??= webcrypto;
const token = "t".repeat(64);
const hash = createHash("sha256").update(token).digest("hex");
const body = "## Human priority feedback\n\nCase: case-1\nGoal: Choose a plan\n\nSource: user_feedback\n";
const item = { id: "case-1", title: "[priority-eval] case-1", body };
const env = {
  GITHUB_TOKEN: "test-github-token",
  UPLOAD_TOKEN_HASHES: hash,
  RATE_LIMITER: { async limit() { return { success: true }; } },
};
const post = (payload, authorization = token) => new Request("https://intake.test/v1/cases", {
  method: "POST",
  headers: { "Content-Type": "application/json", Authorization: `Bearer ${authorization}` },
  body: JSON.stringify(payload),
});

test("authenticated summaries reach only the private issue API", async () => {
  const original = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    return Response.json({ node_id: "I_private_123" }, { status: 201 });
  };
  try {
    assert.equal((await worker.fetch(post(item, "wrong-token"), env)).status, 401);
    assert.equal((await worker.fetch(post({ ...item, artifact: "/private/file" }), env)).status, 400);
    const result = await worker.fetch(post(item), env);
    assert.equal(result.status, 201);
    assert.deepEqual(await result.json(), { receipt: "I_private_123" });
    assert.equal(calls.length, 1);
    assert.equal(calls[0].url, "https://api.github.com/repos/bigshuaige1/agent-eval-data/issues");
    assert.deepEqual(JSON.parse(calls[0].options.body), { title: item.title, body: item.body });
  } finally {
    globalThis.fetch = original;
  }
});

test("oversized submissions stop before GitHub", async () => {
  const result = await worker.fetch(post({ ...item, body: "x".repeat(9000) }), env);
  assert.equal(result.status, 413);
});
