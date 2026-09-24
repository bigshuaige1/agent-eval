// Anonymous intake for short evaluation cases. Keep GITHUB_TOKEN only as a Worker secret.
export default {
  async fetch(request, env) {
    const path = new URL(request.url).pathname;
    if (path !== "/v1/cases" || request.method !== "POST") {
      return new Response("Not found", { status: 404 });
    }
    if (!env.GITHUB_TOKEN || !env.RATE_LIMITER) {
      return new Response("Intake is not configured", { status: 503 });
    }
    const ip = request.headers.get("CF-Connecting-IP") || "unknown";
    const limit = await env.RATE_LIMITER.limit({ key: ip });
    if (!limit.success) {
      return new Response("Too many submissions", { status: 429 });
    }
    if (Number(request.headers.get("content-length")) > 8192) {
      return new Response("Case is too large", { status: 413 });
    }
    let item;
    try {
      const raw = await request.text();
      if (raw.length > 8192) return new Response("Case is too large", { status: 413 });
      item = JSON.parse(raw);
    } catch {
      return new Response("Invalid JSON", { status: 400 });
    }
    if (!item || !/^[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}$/.test(item.id) ||
        item.title !== `[priority-eval] ${item.id}` ||
        typeof item.body !== "string" || item.body.length > 6000 ||
        !item.body.startsWith(`## Human priority feedback\n\nCase: ${item.id}\n`) ||
        !/Source: (user_feedback|independent_review)/.test(item.body)) {
      return new Response("Invalid case", { status: 400 });
    }
    const github = await fetch("https://api.github.com/repos/bigshuaige1/agent-eval-data/issues", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GITHUB_TOKEN}`,
        Accept: "application/vnd.github+json",
        "Content-Type": "application/json",
        "User-Agent": "agent-eval-intake",
      },
      body: JSON.stringify({ title: item.title, body: item.body }),
    });
    if (!github.ok) return new Response("Private intake unavailable", { status: 502 });
    const issue = await github.json();
    return Response.json({ receipt: issue.node_id }, { status: 201 });
  },
};
