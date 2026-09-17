// GET /confirm?token=...&answer=yes|no
// メール内の「はい」「いいえ」リンクの行き先。押した端末（メールを見ている端末）に
// 簡単な確認画面を出す。実際の質問応答システムの画面は、元の端末側でポーリングにより
// 自動的に切り替わる（session-status.js 参照）。

const SESSION_WINDOW_HOURS = 24; // 確認後、質問応答を使える期間

function page(title, message) {
  const html = `<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${title}</title>
<style>
  body{font-family:"Hiragino Mincho ProN","Yu Mincho",serif;background:#fbfbf9;color:#1b1b1b;
       line-height:1.9;margin:0;}
  .wrap{max-width:32em;margin:0 auto;padding:3rem 1.3rem;}
  h1{font-size:1.2rem;}
</style></head>
<body><div class="wrap"><h1>${title}</h1><p>${message}</p></div></body></html>`;
  return new Response(html, { headers: { "content-type": "text/html; charset=utf-8" } });
}

export async function onRequestGet(context) {
  const { request, env } = context;
  const url = new URL(request.url);
  const token = url.searchParams.get("token") || "";
  const answer = url.searchParams.get("answer") || "";

  if (!token || !["yes", "no"].includes(answer)) {
    return page("確認できませんでした", "リンクの形式が正しくありません。");
  }

  const row = await env.DB.prepare(
    `SELECT id, status, confirm_expires_at FROM sessions WHERE token = ?`
  ).bind(token).first();

  if (!row) {
    return page("この確認リンクは無効です", "リンクが正しくないか、すでに処理されています。");
  }
  if (row.status !== "pending") {
    return page("この確認リンクはすでに使われています", "このメールは破棄していただいて結構です。");
  }
  if (new Date(row.confirm_expires_at).getTime() < Date.now()) {
    await env.DB.prepare(`UPDATE sessions SET status = 'expired' WHERE id = ?`).bind(row.id).run();
    return page("確認の期限が切れました", "お手数ですが、最初の画面からもう一度メールアドレスを入力してください。このメールは破棄していただいて結構です。");
  }

  if (answer === "yes") {
    const sessionExpires = new Date(Date.now() + SESSION_WINDOW_HOURS * 60 * 60 * 1000);
    await env.DB.prepare(
      `UPDATE sessions SET status = 'confirmed', confirmed_at = datetime('now'), session_expires_at = ? WHERE id = ?`
    ).bind(sessionExpires.toISOString(), row.id).run();
    return page("確認しました", "元の画面（質問応答システムにアクセスした画面）でご利用いただけます。このメールは破棄していただいて結構です。");
  } else {
    await env.DB.prepare(`UPDATE sessions SET status = 'denied' WHERE id = ?`).bind(row.id).run();
    return page("承知しました", "このメールは破棄していただいて結構です。心当たりのないメールが届いた場合は、念のためご注意ください。");
  }
}
