# -*- coding: utf-8 -*-
r"""
edusalon生のメールアドレス一覧（エクセル）を、Cloudflare D1 の allowlist テーブルへ取り込む。

エクセルの中から「メールアドレスらしいセル」を自動で拾う（列の位置を問わない、簡易な方式）。
同じ行に、メールアドレスでない文字列のセルがあれば、名前として一緒に記録する（無くてもよい）。

使い方:
  python import_allowlist.py "西川さんから受け取ったファイル.xlsx"
  python import_allowlist.py "...xlsx" --dry-run   … 取り込まず、拾った件数だけ確認

環境変数（実行前に設定する）:
  CLOUDFLARE_API_TOKEN   … D1への書き込み権限を持つAPIトークン
  CLOUDFLARE_ACCOUNT_ID
  D1_DATABASE_ID
"""
import os, re, sys, json
from pathlib import Path

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def read_candidates(xlsx_path: Path):
    import openpyxl
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    rows = []
    for ws in wb.worksheets:
        for row in ws.iter_rows(values_only=True):
            cells = [str(c).strip() for c in row if c is not None and str(c).strip()]
            if not cells:
                continue
            email = next((c for c in cells if EMAIL_RE.match(c)), None)
            if not email:
                continue
            name = next((c for c in cells if c != email), "")
            rows.append((email.lower(), name))
    # 重複除去（同じメールが複数シート・複数行にあってもよい）
    seen = {}
    for email, name in rows:
        if email not in seen or (name and not seen[email]):
            seen[email] = name
    return sorted(seen.items())


def d1_query(sql: str, params: list):
    import httpx
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    db_id = os.environ.get("D1_DATABASE_ID", "")
    missing = [n for n, v in [("CLOUDFLARE_API_TOKEN", token), ("CLOUDFLARE_ACCOUNT_ID", account_id),
                               ("D1_DATABASE_ID", db_id)] if not v]
    if missing:
        raise RuntimeError("次の環境変数が未設定です: " + ", ".join(missing))
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/d1/database/{db_id}/query"
    headers = {"Authorization": f"Bearer {token}", "content-type": "application/json"}
    r = httpx.post(url, headers=headers, json={"sql": sql, "params": params}, timeout=30)
    r.raise_for_status()
    data = r.json()
    if not data.get("success"):
        raise RuntimeError(f"D1エラー: {data.get('errors')}")
    return data


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry_run = "--dry-run" in sys.argv
    if not args:
        print(__doc__)
        return
    xlsx_path = Path(args[0])
    if not xlsx_path.exists():
        print(f"ファイルが見つかりません: {xlsx_path}")
        return

    rows = read_candidates(xlsx_path)
    print(f"メールアドレスらしいセルを {len(rows)} 件見つけました。")
    for email, name in rows[:10]:
        print(f"  {email}" + (f"  ({name})" if name else ""))
    if len(rows) > 10:
        print(f"  … 他 {len(rows) - 10} 件")

    if dry_run:
        print("\n--dry-run のため、D1へは書き込んでいません。")
        return

    print("\nD1へ取り込みます…")
    for email, name in rows:
        d1_query(
            "INSERT INTO allowlist (email, name, created_at) VALUES (?, ?, datetime('now')) "
            "ON CONFLICT(email) DO UPDATE SET name = excluded.name",
            [email, name],
        )
    print(f"完了。{len(rows)} 件を allowlist に反映しました。")


if __name__ == "__main__":
    main()
