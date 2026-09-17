// POST /api/request-access  { email }
// メールアドレスを受け取り、許可リストと照合してセッションを作る。
// 許可リストに無い場合も、外からは見分けが付かない同じ応答を返す（メンバーかどうかを漏らさない）。

const CONFIRM_WINDOW_MIN = 30; // 「はい/いいえ」の確認待ちの期限（分）

function isValidEmail(s) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s);
}

export async function onRequestPost(context) {
  const { request, env } = context;
  let body;
  try {
    body = await request.json();
  } catch {
    return Response.json({ error: "invalid json" }, { status: 400 });
  }

  const rawEmail = (body.email || "").trim();
  if (!isValidEmail(rawEmail)) {
    return Response.json({ error: "メールアドレスの形式が正しくありません。" }, { status: 400 });
  }
  const email = rawEmail.toLowerCase();

  // 簡易レート制限：同じメールアドレスから直近60秒以内の未処理リクエストがあれば弾く
  const recent = await env.DB.prepare(
    `SELECT id FROM sessions WHERE email = ? AND created_at > datetime('now', '-60 seconds') LIMIT 1`
  ).bind(email).first();
  if (recent) {
    return Response.json({ error: "少し間隔をあけてから、もう一度お試しください。" }, { status: 429 });
  }

  const member = await env.DB.prepare(
    `SELECT email FROM allowlist WHERE email = ?`
  ).bind(email).first();
  const isMember = !!member;

  const sessionId = crypto.randomUUID();
  const token = crypto.randomUUID();
  const now = new Date();
  const confirmExpires = new Date(now.getTime() + CONFIRM_WINDOW_MIN * 60 * 1000);

  await env.DB.prepare(
    `INSERT INTO sessions (id, email, token, is_member, status, created_at, confirm_expires_at)
     VALUES (?, ?, ?, ?, 'pending', datetime('now'), ?)`
  ).bind(sessionId, email, token, isMember ? 1 : 0, confirmExpires.toISOString()).run();

  if (isMember) {
    const siteBase = env.SITE_BASE_URL;
    const yesUrl = `${siteBase}/confirm?token=${token}&answer=yes`;
    const noUrl = `${siteBase}/confirm?token=${token}&answer=no`;

    const res = await fetch(`${env.RENDER_BACKEND_URL}/send-verification-email`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "X-Internal-Key": env.INTERNAL_SHARED_KEY,
      },
      body: JSON.stringify({ to: email, yes_url: yesUrl, no_url: noUrl }),
    });
    if (!res.ok) {
      // メール送信に失敗しても、メンバーかどうかは漏らさない形の応答にする。
      // ただし運営側が気づけるよう、ログには残す。
      console.error("send-verification-email failed", res.status, await res.text());
    }
  }

  // メンバーであってもなくても、同じ形の応答を返す。
  return Response.json({ sessionId });
}
