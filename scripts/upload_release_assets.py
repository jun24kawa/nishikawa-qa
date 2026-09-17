# -*- coding: utf-8 -*-
r"""
GitHub Releases に、索引ファイル（約194MB）をアップロードする一時スクリプト。
ブラウザのドラッグ＆ドロップが不安定だったため、APIで確実に行う。

使い方:
  $env:GITHUB_TOKEN = "github_pat_..."
  python upload_release_assets.py
"""
import os
from pathlib import Path
import httpx

OWNER = "jun24kawa"
REPO = "nishikawa-qa"
TAG = "index-data-v1"
SRC_DIR = Path(r"C:\Users\jun\Dropbox\Claude Code 作業フォルダー\ゼミYouTube編集")
FILES = ["mini_index_vocab.json", "mini_index_meta.jsonl", "mini_index_lex.npz"]  # 小さい順

CONTENT_TYPES = {
    ".json": "application/json",
    ".jsonl": "application/x-ndjson",
    ".npz": "application/octet-stream",
}


def main():
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        print("環境変数 GITHUB_TOKEN が設定されていません。")
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
                json={"tag_name": TAG, "name": "索引データ v1",
                      "body": "ミニ西川の検索用索引（backend が起動時に取得する）", "draft": False},
            )
            r.raise_for_status()
            release = r.json()
            print(f"新しくリリースを作りました（id={release['id']}）")
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
                print(f"既にアップロード済みなのでスキップ: {name}")
                continue

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
