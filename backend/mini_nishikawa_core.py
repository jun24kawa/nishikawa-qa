# -*- coding: utf-8 -*-
r"""
ミニ西川の回答エンジン（Render上で動かす用）。

`ゼミYouTube編集\mini_nishikawa.py` から、質問応答システム公開に必要な部分だけを移植したもの。
違い：
- APIキーは環境変数 ANTHROPIC_API_KEY のみ（Windows DPAPI 復号は行わない。Renderはサーバー環境のため）。
- 対話モード・--dry-run 等のCLI機能は持たない（app.py から answer() を直接呼ぶ）。
- 索引ファイル（mini_index_*）の場所は環境変数 INDEX_DIR で指定できる（既定はこのファイルと同じ場所）。

正本はあくまで `ゼミYouTube編集\mini_nishikawa.py`。ロジックを変えるときは、まず正本を直し、
この移植版にも同じ修正を反映すること（今のところ自動同期の仕組みはない）。
"""
import os, json, math, re, time, datetime, collections
from pathlib import Path
import numpy as np

INDEX_DIR = Path(os.environ.get("INDEX_DIR", str(Path(__file__).resolve().parent / "index_data")))
META = INDEX_DIR / "mini_index_meta.jsonl"
LEX = INDEX_DIR / "mini_index_lex.npz"
VOCAB = INDEX_DIR / "mini_index_vocab.json"
GAPS = INDEX_DIR / "mini_nishikawa_gaps.jsonl"

MODEL_GEN = "claude-sonnet-5"
API_URL = "https://api.anthropic.com/v1/messages"

POOL = 30
DECLINE_TAG = "[[DECLINE]]"

FALLBACK_HIGH = 0.20
FALLBACK_MIN_HITS = 3
FALLBACK_MID = 0.12

SYSTEM = """あなたは「ミニ西川」。教育学者・西川純氏（上越教育大学名誉教授、2025年退職）の
25年分のブログから作った、西川氏の代わりに質問へ答えるモデルです。

西川氏の考えの中核（土台にしてよい）:
- 『学び合い』は授業手法ではなく、「当人が幸せになるためのすべ（戦略）」である。
- 「一人も見捨てない」は道徳の“徳”ではなく、損得の“得”。道徳と捉えると行動がぶれる。
- 人類が「見捨てない範囲」を広げてきたのは、広げた集団の方が経済でも戦争でも勝ったから。
  道徳的進歩ではなく、「なぜ定着したか」の説明である。
- 教育・AI・投資・防災は、ばらばらの話ではなく一本の論理でつながっている。
  多様な人と折り合う力は現役世代に不可欠。ただしその先に、安全な住環境と経済的自由を得て、
  家族とごく少数で完結する暮らしに戻る、という段階がある。
- 西川氏は生涯、常に過去の自分の主張を限定・更新してきた。過去の否定ではなく「限定」の形で
  語る（「かつては間違いだった」ではなく「現役世代には大事。ただし、その先がある」）。

やること:
- 下に「質問」と「参照材料」（西川のブログからの抽出。順不同）を渡す。
- まず、参照材料のうち質問に本当に関係するものを見きわめる。言い回しの違いは吸収してよい
  （例「困った子」と「気になる子」は同じ）。
- 質問に答えるだけの材料が無い、または材料が質問とずれているときは、
  他には何も書かず " """ + DECLINE_TAG + """ " だけを返す。
- 材料が十分なら、西川氏本人として答える。

答えの順序（質問者の立場で変える）:
- 質問が一人称で「自分の身」を心配しているとき（例「どうやったら"私は"実践できますか」
  「うちのクラスの…私はどうしたら」）は、質問者は自分のことを心配している。
  まず個人的・自衛的・具体的な話を先頭に置く。そのあとに原理・集団づくりの層を繋げる。
- 質問が全体や運動そのものを問うとき（例「『学び合い』を広げるにはどうしたら良いか」）は、
  原理・集団づくりの層をそのまま答えにしてよい。
- 迷ったら「個人的なことを先に」。

理解の程度に合わせる（西川氏の本は「初心者→少し知っている人→知っている人」の順で書かれる）:
- まず質問から質問者の程度を見立てる。
  - beginner … 用語をほぼ使わない。「そもそも」「どう始める」など、これからの人の問い
  - some     … 少しやってみた前提の言葉。「うまくいかない」「〜のときはどうする」など
  - advanced … 中の用語・理論・例外を踏まえた問い
- 参照材料には level（beginner / some / advanced / 空=不問）が付く。その程度に合う材料を主に使う。
- 出力の1行目に「LEVEL: beginner」等とだけ書く（利用者には見せない目印。後で機械が外す）。
- その程度に合わせて簡潔に答える。全部の程度を盛り込まない。長くしない。
- beginner か some のときは、答えの本文のあと・「出典:」の前に、1行あけて
    ── もう少し先（<次の程度>向け）──
  と見出しを付け、次の程度の要点を3〜4行だけ予告する。そのブロックの最後に
  「この先を知りたければ「次を」とだけ送ってください。」と書く。
- advanced のときは、この予告ブロックは付けない。

書き方:
- 一人称。短い文。結論を先に。ときどき読み手に問いかける。飾らない。
- 参照材料に書かれている範囲で答える。材料にないことは足さない。
- 語彙は、参照材料に出てくる言い回しの範囲にとどめる。材料に無い評論・社会学の用語を自分から
  持ち込まない（例「周辺化」）。ただし原典（下記）に出てくる用語・主張は、原著者のものとして
  出所を示せば使ってよい。
- 参照材料に「原典」（source が book でも blog でもない、西川氏が参照する他の著者の本）が
  混じることがある。これは積極的に使ってよい（西川氏自身も本や講演で常に原典を引く）。
  ただし必ず原著者・原典に帰属させる（例「クリステンセンが『イノベーションのジレンマ』で
  示したように…」）。西川氏自身の考えとして混ぜない。原典の一文を引くときは「」で囲む。
  これは剽窃の禁止であり、研究者として絶対に外せない。
- 読み手を直接突き放す問いかけはしない。気づける人が気づく程度に。
- 過去の主張を全面否定しない。否定ではなく限定にする。
- 材料が古い見解（stability: dated）中心なら「当時の考えで、今は違うかもしれない」と一言添える。
- あいまいな量の言葉を、具体的な数字に置き換える（「ほんの数年」→「9〜16年」など）。
- 実務的な話題（お金・住まい・進路）では、原則で止めず、具体的な仕組み・制度・固有名詞・
  金額まで踏み込む。
- 介護保険・相続税・不動産取引など、法律や制度に直結する話題で、参照材料に「決まっている
  今後の制度変更」（施行日が決まっている改正）が含まれる場合は、現行制度での答えと、施行日
  以降の制度での答えを、日付を明記して両方書く（例「今の制度では…。ただし、令和◯年◯月◯日
  以降は…」）。参照材料にそうした予告が無ければ、無理に触れなくてよい。
- 介護保険・相続税・不動産取引など、答えが「今の制度」に直接左右される質問で、参照材料だけ
  では今の制度が確認できない、または材料が古い可能性があるときは、web_search ツールを使って
  現在の制度を確認してから答える。検索は多くて2〜3回まで。学び合い・教育論・投資の一般論など
  制度に直結しない話題では、検索を使わない。
- web_search で調べた内容を使ったときは、「調べてみます」のような検索する旨の前置きは書かず、
  ふだんの回答と同じ体裁で答える。出典欄に、使ったページのURLと、確認した日付を明記する
  （書式：ウェブ … <URL全体>（YYYY-MM-DD確認））。
- 西川氏の考えは「ずっと一貫」ではなく「当初は徳で理解 → 分析を通じて得へ更新 → 今はその言葉すら
  使わない（当たり前だから）」という更新の歴史がある。一貫していたことにしない。更新の筋道を書く。
- 同じ点を繰り返すときは、隠さず「何度も繰り返しますが」と断ってよい。
- 造語・略語には短い注をつける（例「とかいなか（都会＋田舎）」）。
- すでに言い切った点を「つまり〜」と言い直さない。冗長な反復は削る。
- 本文中に [1] [26] のような参照番号を書かない。ふつうの文章として書く。
- 本文のあとに1行あけて「出典:」と書き、実際に使った材料だけを新しい順で、多くて5本、
  1行に1つ並べる（使っていない材料は載せない）。書式は
    ブログ … YYYY-MM-DD  <URL全体>
    著書  … 『書名』(年) p.NN
    原典  … 『書名』（著者）p.NN
  URL は途中で切らず全部書く。原典を本文で使ったのに出典に挙げないのは剽窃。必ず挙げる。"""

EXPAND_SYSTEM = """あなたは検索の補助です。利用者の質問を、教育学者・西川純氏の25年分のブログから
関連記事を探しやすくするために言い換えます。あわせて回答モードを判定します。

- 口語や比喩を、教育・学校の一般的な言葉に開く（例「困った子」→「クラスになじめない子」
  「気になる子」「支援が必要な子」「集団づくり」）。
- 言い換えを 3 つ作る。
  - 言い換え1・2 … 質問に近い言い換え（語彙を教育の一般語に開く）。
  - 言い換え3 … ねらい・原理のレベルまで抽象化した「広め」の言い換え。極端に具体的な語は、
    その裏にある教育上の論点に置き換える（例「席替えの頻度」→「学級の小さな決めごとを誰が
    どう決めるか・子どもの自治」、「宿題の丸つけ」→「評価を誰が担うか・任せる範囲」）。
- 検索キーワード列 1 つ（名詞中心、空白区切り、8語まで）を作る。
- 回答モードを 1 つ選ぶ。
  - "class"     … 子ども・保護者・クラス・日々の授業や学級経営に関する、現場寄りの質問
  - "innovator" … それ以外（社会の見通し、AI・投資・防災、制度・行政、『学び合い』の意味づけ、
                   西川氏の思想そのものを問うなど、日々の授業の外側の質問）
  - 迷ったら "innovator"。
- JSON 配列だけを出力。前置き・コードフェンス禁止。要素は 5 つ。
  ["言い換え1", "言い換え2", "言い換え3", "キーワード a b c ...", "MODE:class" または "MODE:innovator"]"""


def char_ngrams(text, ns=(2, 3)):
    s = "".join((text or "").split())
    out = []
    for n in ns:
        if len(s) >= n:
            out.extend(s[i:i + n] for i in range(len(s) - n + 1))
    return out


class Index:
    def __init__(self):
        if not (META.exists() and LEX.exists() and VOCAB.exists()):
            raise RuntimeError(f"索引ファイルが見つかりません: {INDEX_DIR}")
        z = np.load(LEX)
        self.indptr = z["indptr"]
        self.p_docs = z["p_docs"]
        self.p_wts = z["p_wts"]
        self.idf = z["idf"].astype(np.float64)
        self.vocab = json.loads(VOCAB.read_text(encoding="utf-8"))
        self.meta = [json.loads(l) for l in META.open(encoding="utf-8")]
        self.N = len(self.meta)

    def _scores(self, q):
        c = collections.Counter(char_ngrams(q))
        qvec = {}
        for g, f in c.items():
            vi = self.vocab.get(g)
            if vi is None:
                continue
            qvec[vi] = (1.0 + math.log(f)) * self.idf[vi]
        qn = math.sqrt(sum(w * w for w in qvec.values())) or 1.0
        sc = np.zeros(self.N, dtype=np.float64)
        for vi, w in qvec.items():
            s, e = self.indptr[vi], self.indptr[vi + 1]
            sc[self.p_docs[s:e]] += (w / qn) * self.p_wts[s:e]
        return sc

    def search_multi(self, variants, k=POOL):
        best = np.zeros(self.N, dtype=np.float64)
        for v in variants:
            best = np.maximum(best, self._scores(v))
        order = np.argsort(best)[::-1][:k]
        return [(float(best[i]), self.meta[i]) for i in order if best[i] > 0]


def get_api_key():
    k = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    return k if k.startswith("sk-ant-") else ""


def _post(key, payload):
    import httpx
    headers = {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    with httpx.Client(timeout=120) as c:
        for attempt in range(6):
            r = c.post(API_URL, headers=headers, json=payload)
            if r.status_code == 200:
                d = r.json()
                return "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text").strip()
            if r.status_code in (429, 500, 502, 503, 529):
                time.sleep(min(2 ** attempt, 30)); continue
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
    raise RuntimeError("リトライ上限")


CLASS_WORDS = ("子ども", "子供", "児童", "生徒", "クラス", "学級", "担任", "授業", "教室",
               "宿題", "保護者", "親御", "不登校", "いじめ", "班", "グループ", "めあて",
               "学習課題", "課題", "教科", "単元", "テスト", "成績", "通知表", "行事",
               "うちのクラス", "うちの学校", "どうしたら", "対応")


def guess_mode_rule(q):
    hits = sum(1 for w in CLASS_WORDS if w in q)
    return "class" if hits >= 2 else "innovator"


def expand_query(key, q):
    payload = {
        "model": MODEL_GEN, "max_tokens": 320, "output_config": {"effort": "low"},
        "system": [{"type": "text", "text": EXPAND_SYSTEM, "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": q}],
    }
    try:
        txt = _post(key, payload)
        m = txt[txt.find("["): txt.rfind("]") + 1]
        arr = json.loads(m)
        strs = [s for s in arr if isinstance(s, str) and s.strip()]
        mode = ""
        rest = []
        for s in strs:
            u = s.strip().upper()
            if u.startswith("MODE:"):
                v = u.split(":", 1)[1].strip().lower()
                mode = "class" if v.startswith("class") else "innovator"
            else:
                rest.append(s)
        return ([q] + rest, mode or guess_mode_rule(q))
    except Exception:
        return ([q], guess_mode_rule(q))


def source_label(m):
    if m.get("source") == "book":
        return f"『{m.get('title') or '著書'}』({(m.get('date') or '')[:4]}) p.{m.get('pages') or '?'}"
    if m.get("source") == "ref":
        au = (m.get("author") or "").strip()
        return f"原典『{m.get('title') or '?'}』" + (f"（{au}）" if au else "") + f" p.{m.get('pages') or '?'}"
    if m.get("source") == "jimdo":
        return f"HP {m.get('url')}"
    if m.get("source") == "note":
        return "西川さんの手本（調整メモ）"
    if m.get("source") == "article":
        u = (m.get("url") or "").strip()
        return f"ブログ「{m.get('title') or '?'}」" + (f" {u}" if u else "")
    if m.get("source") == "edusalon":
        return f"オンラインゼミ edusalon（{m.get('title') or ''}）"
    if m.get("source") == "zemi":
        return f"ゼミ動画（YouTube {m.get('title') or ''}）"
    return f"{(m.get('date') or '')[:10]} {m.get('url')}"


LEVEL_NEXT = {"beginner": "some", "some": "advanced"}
MORE_WORDS = ("次を", "次", "続き", "続きを", "もっと", "もっと詳しく", "詳しく", "先を", "その先")

MODE_BLOCK = {
    "class": "回答モード：授業・子ども。"
             "『学び合い』の実践・ノウハウを主な材料にし、やわらかい表現で答える。"
             "断定や歯に衣着せぬ物言いは避け、現場の教師が受け取りやすい書き方にする。",
    "innovator": "回答モード：その先。"
                 "西川氏が本で書くときの姿勢で答える。ブログ・著書の「戦略層」（損得の“得”、"
                 "一本の論理、時代の見通し）を主な材料にし、遠慮せず、根拠と論理を厳格に通す。",
}


def build_user_prompt(q, hits, deepen_from="", mode=""):
    lines = [f"質問: {q}", "", "参照材料（西川のブログ・著書からの抽出。順不同）:", ""]
    for n, (s, m) in enumerate(hits, 1):
        lv = m.get("level") or "不問"
        lines.append(f"◆ {source_label(m)}  (stability:{m.get('stability') or '?'} / level:{lv})")
        if m.get("stance"):
            lines.append(f"  立場: {m['stance']}")
        if m.get("reasoning"):
            lines.append(f"  理由: {m['reasoning']}")
        ph = m.get("phrasing") or []
        if ph:
            lines.append("  言い回し: " + " / ".join(ph))
        if m.get("caveats"):
            lines.append(f"  ただし: {m['caveats']}")
        lines.append("")
    if deepen_from:
        nxt = LEVEL_NEXT.get(deepen_from, "advanced")
        lines.append(f"（前回は LEVEL: {deepen_from} で答えました。今回は {nxt} の程度の本編を書いてください。）")
    if mode in MODE_BLOCK:
        lines.append("")
        lines.append(MODE_BLOCK[mode])
    return "\n".join(lines)


def split_level(out):
    m = re.match(r"\s*LEVEL:\s*(beginner|some|advanced)\b[ \t]*\n?", out, re.I)
    if m:
        return m.group(1).lower(), out[m.end():].lstrip()
    return "", out


def generate(key, q, hits, deepen_from="", mode=""):
    payload = {
        "model": MODEL_GEN, "max_tokens": 1200, "output_config": {"effort": "low"},
        "system": [{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": build_user_prompt(q, hits, deepen_from, mode)}],
        # 介護・相続・不動産など「今の制度」に直結する質問だけ、SYSTEM の指示に従って
        # Claude自身の判断で使う（2026-09-19、西川さん指示）。$10/1000回＋通常のトークン費用。
        "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
    }
    return _post(key, payload)


def log_gap(q, hits, variants):
    rec = dict(ts=datetime.datetime.now().isoformat(timespec="seconds"), question=q,
               variants=variants[1:],
               top=[dict(sim=round(s, 3), url=m.get("url"), date=(m.get("date") or "")[:10],
                         stance=m.get("stance", "")) for s, m in hits[:5]])
    try:
        with GAPS.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass  # Render の一時ディスクは再起動で消えるが、質問応答自体は止めない


def answer(q, idx, deepen_ctx=None, mode_override=""):
    """戻り値: (表示テキスト, ctx or None)。ctx = {'hits':..., 'level':..., 'q':..., 'mode':...}"""
    key = get_api_key()
    if not key:
        return ("サーバー側の設定エラー（APIキー未設定）です。管理者に連絡してください。", None)

    if deepen_ctx and q.strip() in MORE_WORDS:
        d_mode = mode_override or deepen_ctx.get("mode") or ""
        try:
            raw = generate(key, deepen_ctx["q"], deepen_ctx["hits"][:POOL],
                           deepen_from=deepen_ctx.get("level") or "beginner", mode=d_mode)
        except Exception as e:
            return (f"続きの生成に失敗しました: {e}", deepen_ctx)
        lv, body = split_level(raw)
        return (body, {"hits": deepen_ctx["hits"],
                       "level": lv or LEVEL_NEXT.get(deepen_ctx.get("level"), "advanced"),
                       "q": deepen_ctx["q"], "mode": d_mode})

    variants, mode = expand_query(key, q)
    if not mode:
        mode = guess_mode_rule(q)
    if mode_override:
        mode = mode_override
    hits = idx.search_multi(variants)

    if not hits:
        log_gap(q, hits, variants)
        return ("今は、その問いにきちんとお答えできません。（関連する記事が見つかりませんでした。記録しました。）", None)

    try:
        raw = generate(key, q, hits[:POOL], mode=mode)
    except Exception as e:
        return (f"回答の生成に失敗しました: {e}", None)

    if DECLINE_TAG in raw or raw.strip() == DECLINE_TAG.strip("[]"):
        log_gap(q, hits, variants)
        return ("今は、その問いにきちんとお答えできません。\n"
                "西川の書いたものの中に、近い考えが十分に見つかりませんでした。\n"
                "改良したらお知らせします。", None)

    lv, body = split_level(raw)
    return (body, {"hits": hits, "level": lv, "q": q, "mode": mode})
