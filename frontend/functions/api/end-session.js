// POST /api/end-session  { sessionId }
// 「質問応答システムを終了する」ボタン。セッションを無効にする。

export async function onRequestPost(context) {
  const { request, env } = context;
  let body;
  try {
    body = await request.json();
  } catch {
    return Response.json({ error: "invalid json" }, { status: 400 });
  }
  const sessionId = (body.sessionId || "").trim();
  if (!sessionId) {
    return Response.json({ error: "sessionId is required" }, { status: 400 });
  }
  await env.DB.prepare(
    `UPDATE sessions SET status = 'ended' WHERE id = ? AND status = 'confirmed'`
  ).bind(sessionId).run();

  // Render側に覚えさせている「次を」用の文脈も、ここで片付けておく（失敗しても気にしない）。
  context.waitUntil(
    fetch(`${env.RENDER_BACKEND_URL}/end-session`, {
      method: "POST",
      headers: { "content-type": "application/json", "X-Internal-Key": env.INTERNAL_SHARED_KEY },
      body: JSON.stringify({ session_id: sessionId }),
      signal: AbortSignal.timeout(5000),
    }).catch(() => {})
  );

  return Response.json({ ok: true });
}
