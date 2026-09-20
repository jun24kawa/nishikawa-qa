# -*- coding: utf-8 -*-
r"""
GitHub Releases に、索引ファイル（約194MB）をアップロードする。

既存の同名アセットがあれば削除してから、新しいものをアップロードする（同じタグを使い回せる）。
2026-09-20：fine-grainedトークンではReleases APIの削除操作が403になったため、
classic トークン（repoスコープ）を使うこと。

トークンの取得順:
  1. 環境変数 GITHUB_TOKEN
  2. %USERPROFILE%\.github\github_pat.dat（DPAPI暗号化、GitHubトークン設定.ps1で保存）
     期限切れ等で復号したトークンが401になったら、GitHubで新しいトークン（classic、repoスコープ、
     長期の有効期限）を発行しますが、よろしいですか、と西川さんに確認してから作り直すこと。

使い方:
  python upload_release_assets.py
"""
import os
import ctypes
import ctypes.wintypes as wt
from pathlib import Path
import httpx

OWNER = "jun24kawa"
REPO = "nishikawa-qa"
TAG = "index-data-v2"
SRC_DIR = Path(r"C:\Users\jun\Dropbox\Claude Code 作業フォルダー\ゼミYouTube編集")
FILES = ["mini_index_vocab.json", "mini_index_meta.jsonl", "mini_index_lex.npz"]  # 小さい順

CONTENT_TYPES = {
    ".json": "application/json",
    ".jsonl": "application/x-ndjson",
    ".npz": "application/octet-stream",
}


def get_github_token():
    tok = os.environ.get("GITHUB_TOKEN", "").strip()
    if tok:
        return tok
    dat = Path(os.path.expanduser("~")) / ".github" / "github_pat.dat"
    if not dat.exists():
        return ""
    try:
        b = dat.read_bytes()
        class BLOB(ctypes.Structure):
            _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]
        buf = ctypes.create_string_buffer(b, len(b))
        bi = BLOB(len(b), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
        bo = BLOB()
        if ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(bi), None, None, None, None, 0, ctypes.byref(bo)):
            out = ctypes.string_at(bo.pbData, bo.cbData).decode("utf-8").strip()
            ctypes.windll.kernel32.LocalFree(bo.pbData)
            return out
    except Exception as e:
        print(f"(トークン復号に失敗: {e})", flush=True)
    return ""


def main():
    token = get_github_token()
    if not token:
        print("GITHUB_TOKEN が取得できません。GitHubトークン設定.ps1 を実行するか、"
              "環境変数 GITHUB_TOKEN を設定してください。")
        return
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    with httpx.Client(headers=headers, timeout=None) as c:
        # リリースを取得（無ければ作る）
        r = c.get(f"https://api.github.com/repos/{OWNER}/{REPO}/releases/tags/{TAG}")
        if r.status_code == 200:
            release = r.json()
            print(f"既存のリリースを使います（id={release['id']}）")
        elif r.status_code == 404:
            r = c.post(
                f"https://api.github.com/repos/{OWNER}/{REPO}/releases",
                json={"tag_name": TAG, "name": "索引データ",
                      "body": "ミニ西川の検索用索引（backend が起動時に取得する）", "draft": False},
            )
            if r.status_code == 401:
                print("認証に失敗しました（401）。トークンの期限切れの可能性があります。"
                      "西川さんに新しいトークンの発行を確認してください。")
                return
            r.raise_for_status()
            release = r.json()
            print(f"新しくリリースを作りました（id={release['id']}）")
        elif r.status_code == 401:
            print("認証に失敗しました（401）。トークンの期限切れの可能性があります。"
                  "西川さんに新しいトークンの発行を確認してください。")
            return
        else:
            r.raise_for_status()

        release_id = release["id"]
        existing = {a["name"]: a["id"] for a in release.get("assets", [])}

        for name in FILES:
            path = SRC_DIR / name
            if not path.exists():
                print(f"!! 見つかりません: {path}")
                continue

            if name in existing:
                print(f"既存を削除中: {name}（asset_id={existing[name]}）", flush=True)
                dr = c.delete(f"https://api.github.com/repos/{OWNER}/{REPO}/releases/assets/{existing[name]}")
                if dr.status_code >= 300:
                    print(f"  !! 削除失敗 {dr.status_code}: {dr.text[:300]}（そのまま上書きアップロードを試みます）")

            ctype = CONTENT_TYPES.get(path.suffix, "application/octet-stream")
            size_mb = path.stat().st_size / 1_000_000
            print(f"アップロード中: {name}（{size_mb:.1f}MB, {ctype}）…", flush=True)

            upload_url = (
                f"https://uploads.github.com/repos/{OWNER}/{REPO}/releases/{release_id}/assets"
                f"?name={name}"
            )
            with path.open("rb") as f:
                data = f.read()
            resp = c.post(
                upload_url,
                content=data,
                headers={**headers, "Content-Type": ctype},
            )
            if resp.status_code >= 300:
                print(f"  !! 失敗 {resp.status_code}: {resp.text[:500]}")
            else:
                print(f"  完了: {name}", flush=True)

    print("\n===== 完了 =====")


if __name__ == "__main__":
    main()
