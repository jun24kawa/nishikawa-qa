# -*- coding: utf-8 -*-
r"""
ミニ西川の索引ファイル（約194MB）を Cloudflare R2 へアップロードする。

索引を作り直した（mini_nishikawa_build.py を再実行した）ときは、このスクリプトも
再実行して、Renderが使う索引を最新にすること。

使い方:
  python upload_index_to_r2.py

環境変数（実行前に設定するか、下の CONFIG を直接書き換える）:
  R2_ENDPOINT           例）https://<account_id>.r2.cloudflarestorage.com
  R2_BUCKET             バケット名
  R2_ACCESS_KEY_ID
  R2_SECRET_ACCESS_KEY
"""
import os
from pathlib import Path

SRC_DIR = Path(r"C:\Users\jun\Dropbox\Claude Code 作業フォルダー\ゼミYouTube編集")
FILES = ["mini_index_lex.npz", "mini_index_meta.jsonl", "mini_index_vocab.json"]


def main():
    endpoint = os.environ.get("R2_ENDPOINT", "")
    bucket = os.environ.get("R2_BUCKET", "")
    key_id = os.environ.get("R2_ACCESS_KEY_ID", "")
    secret = os.environ.get("R2_SECRET_ACCESS_KEY", "")
    missing = [n for n, v in [("R2_ENDPOINT", endpoint), ("R2_BUCKET", bucket),
                               ("R2_ACCESS_KEY_ID", key_id), ("R2_SECRET_ACCESS_KEY", secret)] if not v]
    if missing:
        print("次の環境変数が設定されていません: " + ", ".join(missing))
        print("先に $env:R2_ENDPOINT='...' のように設定してから実行してください。")
        return

    import boto3
    s3 = boto3.client("s3", endpoint_url=endpoint,
                       aws_access_key_id=key_id, aws_secret_access_key=secret,
                       region_name="auto")

    for name in FILES:
        src = SRC_DIR / name
        if not src.exists():
            print(f"!! 見つかりません: {src}")
            continue
        size_mb = src.stat().st_size / 1_000_000
        print(f"アップロード中: {name}（{size_mb:.1f}MB）…", flush=True)
        s3.upload_file(str(src), bucket, name)
        print(f"  完了: {name}", flush=True)

    print("\n===== 完了 =====")


if __name__ == "__main__":
    main()
