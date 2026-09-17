# -*- coding: utf-8 -*-
r"""
質問応答システムのバックエンド（Render で常時起動する想定）。

役割：
- 起動時に、索引ファイル（約194MB）が無ければ GitHub Releases からダウンロードする。
- POST /ask を、Cloudflare Pages Functions からの呼び出しだけに限定して受け付け、
  ミニ西川の回答エンジン（mini_nishikawa_core.py）を呼んで JSON で返す。
- GET /health はRenderのヘルスチェック・起動確認用（認証不要、何もしない）。

環境変数（Renderのダッシュボードで設定する）：
  ANTHROPIC_API_KEY   … Claude APIキー
  INTERNAL_SHARED_KEY … Cloudflare側と共有する合言葉（/ask 呼び出しの認証用）
  GMAIL_FROM / GMAIL_APP_PASSWORD … 確認メール送信用（mailer.py参照）
  INDEX_DIR           … 省略可。既定はこのファイルと同じ場所の index_data/

索引ファイルを作り直したときは、scripts/upload_release_assets.py で
GitHub Releases（タグ index-data-v1）へ再アップロードすること。
"""
import os, sys, io
from pathlib import Path
from flask import Flask, request, jsonify

INDEX_DIR = Path(os.environ.get("INDEX_DIR", str(Path(__file__).resolve().parent / "index_data")))
INDEX_FILES = ["mini_index_lex.npz", "mini_index_meta.jsonl", "mini_index_vocab.json"]
RELEASE_BASE = "https://github.com/jun24kawa/nishikawa-qa/releases/download/index-data-v1"


def ensure_index_files():
    """索引ファイルがローカルに無ければ GitHub Releases から取ってくる（公開URL、認証不要）。"""
    import httpx

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    missing = [f for f in INDEX_FILES if not (INDEX_DIR / f).exists()]
    if not missing:
        print(f"索引ファイルは既にあります: {INDEX_DIR}", flush=True)
        return

    with httpx.Client(follow_redirects=True, timeout=300) as c:
        for f in missing:
            url = f"{RELEASE_BASE}/{f}"
            dest = INDEX_DIR / f
            print(f"ダウンロード中: {f} … ({url})", flush=True)
            with c.stream("GET", url) as r:
                r.raise_for_status()
                with dest.open("wb") as out:
                    for chunk in r.iter_bytes(chunk_size=1 << 20):
                        out.write(chunk)
            print(f"  完了 {f}（{dest.stat().st_size:,} bytes）", flush=True)


ensure_index_files()

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mini_nishikawa_core as mn  # noqa: E402
import mailer  # noqa: E402

print("索引を読み込み中…", flush=True)
IDX = mn.Index()
print(f"索引 {IDX.N:,} 記事。準備完了。", flush=True)

app = Flask(__name__)


def check_auth():
    expected = os.environ.get("INTERNAL_SHARED_KEY", "")
    got = request.headers.get("X-Internal-Key", "")
    return bool(expected) and got == expected


@app.route("/health", methods=["GET"])
def health():
    return jsonify(ok=True, articles=IDX.N)


@app.route("/ask", methods=["POST"])
def ask():
    if not check_auth():
        return jsonify(error="unauthorized"), 401

    data = request.get_json(silent=True) or {}
    q = (data.get("question") or "").strip()
    if not q:
        return jsonify(error="question is empty"), 400
    if len(q) > 2000:
        return jsonify(error="question too long"), 400

    debug = bool(data.get("debug"))
    dbg = {}
    if debug:
        import numpy as np
        variants, mode = mn.expand_query(mn.get_api_key(), q)
        hits = IDX.search_multi(variants)
        sample_ng = mn.char_ngrams(q)[:5]
        ng_lookup = {g: IDX.vocab.get(g) for g in sample_ng}
        dbg = {
            "received_question_repr": repr(q),
            "received_question_len": len(q),
            "variants": variants,
            "mode": mode,
            "hits_count": len(hits),
            "top_hits": [{"score": s, "url": m.get("url") or m.get("title")} for s, m in hits[:5]],
            "index_dir": str(mn.INDEX_DIR),
            "file_sizes": {f: (mn.INDEX_DIR / f).stat().st_size for f in ["mini_index_lex.npz", "mini_index_meta.jsonl", "mini_index_vocab.json"]},
            "vocab_size": len(IDX.vocab),
            "idf_shape": list(IDX.idf.shape),
            "idf_sample": IDX.idf[:5].tolist(),
            "idf_nonzero_count": int((IDX.idf != 0).sum()),
            "indptr_shape": list(IDX.indptr.shape),
            "p_docs_shape": list(IDX.p_docs.shape),
            "sample_ngrams": sample_ng,
            "sample_ngram_vocab_lookup": ng_lookup,
            "p_wts_shape": list(IDX.p_wts.shape),
            "p_wts_sample": IDX.p_wts[:5].tolist(),
            "p_wts_dtype": str(IDX.p_wts.dtype),
            "p_docs_dtype": str(IDX.p_docs.dtype),
            "indptr_dtype": str(IDX.indptr.dtype),
        }
        raw_scores = IDX._scores(q)
        dbg["raw_scores_nonzero"] = int((raw_scores > 0).sum())
        dbg["raw_scores_max"] = float(raw_scores.max())
        dbg["raw_scores_dtype"] = str(raw_scores.dtype)
        dbg["raw_scores_shape"] = list(raw_scores.shape)
        dbg["N"] = IDX.N
        vi_kyoshi = IDX.vocab.get("教師")
        if vi_kyoshi is not None:
            s, e = int(IDX.indptr[vi_kyoshi]), int(IDX.indptr[vi_kyoshi + 1])
            dbg["kyoshi_vocab_index"] = vi_kyoshi
            dbg["kyoshi_range"] = [s, e]
            dbg["kyoshi_doc_count"] = e - s
            dbg["kyoshi_sample_docs"] = IDX.p_docs[s:s + 5].tolist()
            dbg["kyoshi_sample_wts"] = IDX.p_wts[s:s + 5].tolist()
            dbg["kyoshi_idf"] = float(IDX.idf[vi_kyoshi])

    try:
        text, ctx = mn.answer(q, IDX)
    except Exception as e:
        return jsonify(error=f"internal error: {e}", debug=dbg), 500

    return jsonify(answer=text, debug=dbg)


EMAIL_TEXT_TMPL = """今、あなたはオンラインゼミ生にのみ公開されている質問応答システムにアクセスしましたか？
回答の上、このメールは廃棄しても結構です。

はい：{yes_url}

いいえ：{no_url}
"""

EMAIL_HTML_TMPL = """\
<div style="font-family:'Hiragino Mincho ProN','Yu Mincho',serif;color:#1b1b1b;
            line-height:1.9;max-width:32em;margin:0 auto;padding:1.5rem;">
  <p>今、あなたはオンラインゼミ生にのみ公開されている質問応答システムにアクセスしましたか？<br>
  回答の上、このメールは廃棄しても結構です。</p>
  <p style="margin:2rem 0;">
    <a href="{yes_url}"
       style="display:inline-block;padding:.7rem 1.6rem;margin-right:1rem;
              background:#8a4b2f;color:#fff;text-decoration:none;border-radius:6px;">はい</a>
    <a href="{no_url}"
       style="display:inline-block;padding:.7rem 1.6rem;
              background:#e2e0da;color:#1b1b1b;text-decoration:none;border-radius:6px;">いいえ</a>
  </p>
</div>
"""


@app.route("/send-verification-email", methods=["POST"])
def send_verification_email():
    if not check_auth():
        return jsonify(error="unauthorized"), 401

    data = request.get_json(silent=True) or {}
    to_addr = (data.get("to") or "").strip()
    yes_url = (data.get("yes_url") or "").strip()
    no_url = (data.get("no_url") or "").strip()
    if not (to_addr and yes_url and no_url):
        return jsonify(error="to / yes_url / no_url is required"), 400

    try:
        mailer.send_mail(
            to_addr,
            subject="質問応答システムへのアクセス確認",
            body_text=EMAIL_TEXT_TMPL.format(yes_url=yes_url, no_url=no_url),
            body_html=EMAIL_HTML_TMPL.format(yes_url=yes_url, no_url=no_url),
        )
    except Exception as e:
        return jsonify(error=f"mail send failed: {e}"), 500

    return jsonify(ok=True)


if __name__ == "__main__":
    # ローカル動作確認用。本番はRenderが gunicorn 経由で起動する。
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
