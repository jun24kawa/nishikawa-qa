// GET /api/ask-status?askId=...
// 質問への回答が出来たかどうかをポーリングで確認する窓口。
//
// まだ処理中（processing）なら、ここで実際に Render を呼びに行く（短い時間だけ）。
// Renderが休止から起きている途中で間に合わなければ、状態を processing に戻すだけにして、
// 次のポーリング（数秒後）でまた試す。こうすることで、Renderの起き上がりが何分かかっても、
// ポーリングを続けている限り必ずいつかは答えにたどり着ける（単発のタイムアウトで詰まらない）。

const RENDER_TIMEOUT_MS = 20000; // 1回のポーリングで待つ上限
const GIVE_UP_AFTER_MS = 4 * 60 * 1000; // これ以上待たせない（4分）

export async function onRequestGet(context) {
  const { env } = context;
  const url = new URL(context.request.url);
  const askId = url.searchParams.get("askId") || "";
  if (!askId) {
    return Response.json({ status: "not_found" }, { status: 400 });
  }

  const row = await env.DB.prepare(
    `SELECT id, session_id, question, status, answer, error, created_at FROM asks WHERE id = ?`
  ).bind(askId).first();

  if (!row) {
    return Response.json({ status: "not_found" });
  }

  if (row.status === "done" || row.status === "error") {
    return Response.json({ status: row.status, answer: row.answer || "", error: row.error || "" });
  }

  if (row.status === "in_flight") {
    // 他のポーリングが今まさに試している最中。今回は何もせず、待っているように見せる。
    return Response.json({ status: "processing" });
  }

  // ここに来るのは status === "processing" のとき。
  const elapsed = Date.now() - new Date(row.created_at + "Z").getTime();
  if (elapsed > GIVE_UP_AFTER_MS) {
    await env.DB.prepare(
      `UPDATE asks SET status = 'error', error = ? WHERE id = ?`
    ).bind("回答エンジンの起動に時間がかかりすぎました。時間をおいてもう一度お試しください。", askId).run();
    return Response.json({ status: "error", error: "回答エンジンの起動に時間がかかりすぎました。時間をおいてもう一度お試しください。" });
  }

  // 「今回はこのポーリングが担当する」という権利を取りに行く（他のポーリングと二重に呼ばないため）。
  const claim = await env.DB.prepare(
    `UPDATE asks SET status = 'in_flight' WHERE id = ? AND status = 'processing'`
  ).bind(askId).run();

  if (!claim.meta || claim.meta.changes !== 1) {
    // 取れなかった＝別のポーリングが今取った。待っているように見せる。
    return Response.json({ status: "processing" });
  }

  try {
    const upstream = await fetch(`${env.RENDER_BACKEND_URL}/ask`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "X-Internal-Key": env.INTERNAL_SHARED_KEY,
      },
      body: JSON.stringify({ question: row.question, session_id: row.session_id }),
      signal: AbortSignal.timeout(RENDER_TIMEOUT_MS),
    });

    if (!upstream.ok) {
      await env.DB.prepare(`UPDATE asks SET status = 'processing' WHERE id = ?`).bind(askId).run();
      return Response.json({ status: "processing" });
    }

    const data = await upstream.json();
    await env.DB.prepare(
      `UPDATE asks SET status = 'done', answer = ? WHERE id = ?`
    ).bind(data.answer || "", askId).run();
    return Response.json({ status: "done", answer: data.answer || "" });
  } catch (e) {
    // タイムアウトや接続エラー。まだ諦めない。processing に戻して次のポーリングに委ねる。
    await env.DB.prepare(`UPDATE asks SET status = 'processing' WHERE id = ?`).bind(askId).run();
    return Response.json({ status: "processing" });
  }
}
