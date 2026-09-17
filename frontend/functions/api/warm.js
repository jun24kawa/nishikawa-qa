// GET /api/warm
// 質問応答画面が開いたタイミングで呼んでおき、Renderを早めに起こしておくためのもの。
// 結果は使わない（起こすことだけが目的）ので、失敗しても気にしない。

export async function onRequestGet(context) {
  const { env } = context;
  const ping = fetch(`${env.RENDER_BACKEND_URL}/health`, { signal: AbortSignal.timeout(20000) })
    .catch(() => {}); // 無視してよい。ここでの成否はユーザーには関係ない。
  context.waitUntil(ping);
  return Response.json({ ok: true });
}
