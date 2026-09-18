// POST /api/feedback  { message, website }
// 本の公開サイト（jun24kawa.github.io、別ドメインの静的サイト）の「ご意見箱」から送られる。
// 名前・メールアドレスは受け取らない（個人情報を集めない設計）。
// `website` はスパム対策のハニーポット欄（人間には見えない。埋まっていたら黙って捨てる）。

const ALLOWED_ORIGIN = "https://jun24kawa.github.io";
const MAX_LEN = 4000;

function corsHeaders() {
  return {
    "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "content-type",
  };
}

export async function onRequestOptions() {
  return new Response(null, { status: 204, headers: corsHeaders() });
}

export async function onRequestPost(context) {
  const { request, env } = context;
  const headers = { ...corsHeaders(), "content-type": "application/json" };

  let body;
  try {
    body = await request.json();
  } catch {
    return new Response(JSON.stringify({ error: "invalid json" }), { status: 400, headers });
  }

  // ハニーポット：人間には見えない欄が埋まっていたら、ボットとみなして黙って成功扱いにする。
  if ((body.website || "").trim()) {
    return new Response(JSON.stringify({ ok: true }), { status: 200, headers });
  }

  const message = (body.message || "").trim();
  if (!message) {
    return new Response(JSON.stringify({ error: "内容が入力されていません。" }), { status: 400, headers });
  }
  if (message.length > MAX_LEN) {
    return new Response(JSON.stringify({ error: `${MAX_LEN}文字以内でお書きください。` }), { status: 400, headers });
  }

  // 簡易レート制限：同じIPから直近60秒以内の投稿があれば弾く。
  const ip = request.headers.get("CF-Connecting-IP") || "unknown";
  const recent = await env.DB.prepare(
    `SELECT id FROM opinions WHERE ip = ? AND created_at > datetime('now', '-60 seconds') LIMIT 1`
  ).bind(ip).first();
  if (recent) {
    return new Response(JSON.stringify({ error: "少し間隔をあけてから、もう一度お試しください。" }), { status: 429, headers });
  }

  await env.DB.prepare(
    `INSERT INTO opinions (id, message, ip, created_at) VALUES (?, ?, ?, datetime('now'))`
  ).bind(crypto.randomUUID(), message, ip).run();

  return new Response(JSON.stringify({ ok: true }), { status: 200, headers });
}
