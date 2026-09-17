// GET /api/ask-status?askId=...
// 質問への回答が出来たかどうかをポーリングで確認する窓口。

export async function onRequestGet(context) {
  const { request, env } = context;
  const url = new URL(request.url);
  const askId = url.searchParams.get("askId") || "";
  if (!askId) {
    return Response.json({ status: "not_found" }, { status: 400 });
  }

  const row = await env.DB.prepare(
    `SELECT status, answer, error FROM asks WHERE id = ?`
  ).bind(askId).first();

  if (!row) {
    return Response.json({ status: "not_found" });
  }

  return Response.json({ status: row.status, answer: row.answer || "", error: row.error || "" });
}
