// GET /api/warm
// 質問応答画面が開いたタイミングで呼んでおき、Renderを早めに起こしておくためのもの。
// 結果は使わない（起こすことだけが目的）ので、失敗しても気にしない。
//
// ついでに、10日を過ぎた質問・回答（asks）と、古いセッション（sessions）を消す。
// 「会話者と会話の内容を、応答がおかしいときの検討材料として一時的に残すが、10日で消す」
// という西川さんの方針（2026-09-19）による。専用のスケジュールタスクを新設する代わりに、
// この画面が開かれるたびに（＝実質ほぼ毎日）ついでに掃除する方式にした。

const RETENTION_DAYS = 10;

async function purgeOldRecords(env) {
  try {
    await env.DB.prepare(
      `DELETE FROM asks WHERE created_at < datetime('now', ?)`
    ).bind(`-${RETENTION_DAYS} days`).run();
    await env.DB.prepare(
      `DELETE FROM sessions WHERE created_at < datetime('now', ?)`
    ).bind(`-${RETENTION_DAYS} days`).run();
  } catch (e) {
    // 掃除に失敗しても、質問応答システムの利用には影響させない。
  }
}

export async function onRequestGet(context) {
  const { env } = context;
  const ping = fetch(`${env.RENDER_BACKEND_URL}/health`, { signal: AbortSignal.timeout(20000) })
    .catch(() => {}); // 無視してよい。ここでの成否はユーザーには関係ない。
  context.waitUntil(ping);
  context.waitUntil(purgeOldRecords(env));
  return Response.json({ ok: true });
}
