// GET /api/session-status?sessionId=...
// 初期画面が、確認メールの「はい」が押されたかどうかをポーリングで確認するための窓口。

export async function onRequestGet(context) {
  const { request, env } = context;
  const url = new URL(request.url);
  const sessionId = url.searchParams.get("sessionId") || "";
  if (!sessionId) {
    return Response.json({ status: "not_found" }, { status: 400 });
  }

  const row = await env.DB.prepare(
    `SELECT status, confirm_expires_at, session_expires_at FROM sessions WHERE id = ?`
  ).bind(sessionId).first();

  if (!row) {
    return Response.json({ status: "not_found" });
  }

  if (row.status === "pending" && new Date(row.confirm_expires_at).getTime() < Date.now()) {
    await env.DB.prepare(`UPDATE sessions SET status = 'expired' WHERE id = ?`).bind(sessionId).run();
    return Response.json({ status: "expired" });
  }

  if (row.status === "confirmed" && row.session_expires_at &&
      new Date(row.session_expires_at).getTime() < Date.now()) {
    return Response.json({ status: "session_expired" });
  }

  return Response.json({ status: row.status });
}
