// POST /api/ask  { sessionId, question }
// 確認済みセッションだけ受け付ける。Renderの回答エンジンは起き上がりに時間がかかることが
// あるため、ここでは待たずに { askId } を返し、実際の問い合わせはバックグラウンドで進める。
// 結果は ask-status.js をポーリングして取りに来る。

export async function onRequestPost(context) {
  const { request, env } = context;
  let body;
  try {
    body = await request.json();
  } catch {
    return Response.json({ error: "invalid json" }, { status: 400 });
  }

  const sessionId = (body.sessionId || "").trim();
  const question = (body.question || "").trim();
  if (!sessionId || !question) {
    return Response.json({ error: "sessionId / question is required" }, { status: 400 });
  }
  if (question.length > 2000) {
    return Response.json({ error: "質問が長すぎます（2000文字まで）。" }, { status: 400 });
  }

  const row = await env.DB.prepare(
    `SELECT status, session_expires_at FROM sessions WHERE id = ?`
  ).bind(sessionId).first();

  if (!row || row.status !== "confirmed") {
    return Response.json({ error: "セッションが確認されていません。最初からやり直してください。" }, { status: 401 });
  }
  if (row.session_expires_at && new Date(row.session_expires_at).getTime() < Date.now()) {
    return Response.json({ error: "利用時間の期限が切れました。最初からやり直してください。" }, { status: 401 });
  }

  await env.DB.prepare(
    `UPDATE sessions SET last_used_at = datetime('now') WHERE id = ?`
  ).bind(sessionId).run();

  const askId = crypto.randomUUID();
  await env.DB.prepare(
    `INSERT INTO asks (id, session_id, question, status, created_at)
     VALUES (?, ?, ?, 'processing', datetime('now'))`
  ).bind(askId, sessionId, question).run();

  context.waitUntil(processAsk(env, askId, question));

  return Response.json({ askId });
}

async function processAsk(env, askId, question) {
  try {
    const upstream = await fetch(`${env.RENDER_BACKEND_URL}/ask`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "X-Internal-Key": env.INTERNAL_SHARED_KEY,
      },
      body: JSON.stringify({ question }),
      signal: AbortSignal.timeout(170000), // Renderの起き上がり待ちを見込んだ余裕
    });

    if (!upstream.ok) {
      await env.DB.prepare(
        `UPDATE asks SET status = 'error', error = ? WHERE id = ?`
      ).bind(`回答エンジンがエラーを返しました（${upstream.status}）。`, askId).run();
      return;
    }

    const data = await upstream.json();
    await env.DB.prepare(
      `UPDATE asks SET status = 'done', answer = ? WHERE id = ?`
    ).bind(data.answer || "", askId).run();
  } catch (e) {
    await env.DB.prepare(
      `UPDATE asks SET status = 'error', error = ? WHERE id = ?`
    ).bind("回答エンジンに接続できませんでした。時間をおいてもう一度お試しください。", askId).run();
  }
}
