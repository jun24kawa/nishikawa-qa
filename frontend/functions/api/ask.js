// POST /api/ask  { sessionId, question }
// 確認済みセッションだけ受け付ける。ここでは Render を呼ばず、D1 に「処理待ち」の行を
// 作って { askId } を返すだけ。実際に Render を呼ぶのは ask-status.js（フロントのポーリング）
// 側で行う。理由：Renderが休止から起きるのに1分以上かかることがあり、Cloudflare Pages
// Functions の waitUntil（バックグラウンド処理）には時間の上限があるため、そこに賭けると
// 「起きるのに時間がかかった日だけ何も起きない」という事故が起きる（2026-09-18に発生）。
// ポーリングのたびに短い時間だけ試す方式に変えることで、何回再試行しても必ず前に進む。

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

  return Response.json({ askId });
}
