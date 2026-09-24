// Public HTTPS intake. Only short, authenticated case summaries reach GitHub.
const ISSUE_URL = "https://api.github.com/repos/bigshuaige1/agent-eval-data/issues";
const MAX_BYTES = 8192;
const CASE_ID = /^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$/;
const HASH = /^[0-9a-f]{64}$/;
const RECEIPT = /^[A-Za-z0-9_-]{1,200}={0,2}$/;

function response(status, data) {
  return Response.json(data, { status });
}

function same(a, b) {
  let difference = a.length ^ b.length;
  for (let i = 0; i < Math.max(a.length, b.length); i++) {
    difference |= (a.charCodeAt(i) || 0) ^ (b.charCodeAt(i) || 0);
  }
  return difference === 0;
}

async function tokenDigest(header, hashes) {
  if (!header?.startsWith("Bearer ")) return null;
  const token = header.slice(7);
  if (token.length < 32 || token.length > 256) return null;
  const digest = [...new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(token)))].map(
    (byte) => byte.toString(16).padStart(2, "0"),
  ).join("");
  let matched = false;
  for (const hash of hashes) matched = same(digest, hash) || matched;
  return matched ? digest : null;
}

async function readBody(request) {
  const length = Number(request.headers.get("Content-Length"));
  if (length > MAX_BYTES) return null;
  const reader = request.body?.getReader();
  if (!reader) return new Uint8Array();
  const chunks = [];
  let total = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > MAX_BYTES) {
      await reader.cancel();
      return null;
    }
    chunks.push(value);
  }
  const bytes = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return bytes;
}

function validCase(item) {
  return item && typeof item === "object" && !Array.isArray(item) &&
    Object.keys(item).sort().join(",") === "body,id,title" &&
    typeof item.id === "string" && CASE_ID.test(item.id) &&
    item.title === `[priority-eval] ${item.id}` &&
    typeof item.body === "string" && item.body.length <= 6000 &&
    item.body.startsWith(`## Human priority feedback\n\nCase: ${item.id}\n`) &&
    /^Source: (user_feedback|independent_review)$/m.test(item.body);
}

export default {
  async fetch(request, env) {
    const path = new URL(request.url).pathname;
    if (path === "/healthz" && request.method === "GET") return response(200, { status: "ok" });
    if (path !== "/v1/cases" || request.method !== "POST") return response(404, { error: "not found" });
    const hashes = env.UPLOAD_TOKEN_HASHES?.split(/\s+/).filter(Boolean);
    if (!env.GITHUB_TOKEN || !hashes?.length || hashes.some((hash) => !HASH.test(hash)) || !env.RATE_LIMITER) {
      return response(503, { error: "intake unavailable" });
    }
    const digest = await tokenDigest(request.headers.get("Authorization"), hashes);
    if (!digest) return response(401, { error: "unauthorized" });
    const limit = await env.RATE_LIMITER.limit({ key: digest });
    if (!limit.success) return response(429, { error: "too many submissions" });
    if (!request.headers.get("Content-Type")?.startsWith("application/json")) {
      return response(415, { error: "JSON required" });
    }
    let item;
    try {
      const bytes = await readBody(request);
      if (!bytes) return response(413, { error: "invalid body size" });
      item = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
    } catch {
      return response(400, { error: "invalid JSON" });
    }
    if (!validCase(item)) return response(400, { error: "invalid case" });
    let github;
    try {
      github = await fetch(ISSUE_URL, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${env.GITHUB_TOKEN}`,
          Accept: "application/vnd.github+json",
          "Content-Type": "application/json",
          "User-Agent": "agent-eval-intake",
        },
        body: JSON.stringify({ title: item.title, body: item.body }),
      });
      if (!github.ok) return response(502, { error: "private repository unavailable" });
      const receipt = (await github.json()).node_id;
      if (typeof receipt !== "string" || !RECEIPT.test(receipt)) {
        return response(502, { error: "private repository unavailable" });
      }
      return response(201, { receipt });
    } catch {
      return response(502, { error: "private repository unavailable" });
    }
  },
};
