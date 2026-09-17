# -*- coding: utf-8 -*-
r"""
確認メールの送信（SendGrid、HTTP API経由）。

Renderの無料プランはSMTP（Gmail送信に使うポート）への接続をブロックしているため、
2026-09-17、smtplib（Gmail直接）からSendGridのHTTP APIへ切り替えた。
送信元アドレス自体は、引き続き西川さんのGmailアドレス（Single Sender Verification済み）を使う。

環境変数：
  SENDGRID_API_KEY … SendGridのAPIキー
  GMAIL_FROM       … 送信元アドレス（SendGridでSingle Sender Verification済みのもの）
"""
import os
import httpx

SENDGRID_URL = "https://api.sendgrid.com/v3/mail/send"


def send_mail(to_addr: str, subject: str, body_text: str, body_html: str = "") -> None:
    api_key = os.environ.get("SENDGRID_API_KEY", "").strip()
    from_addr = os.environ.get("GMAIL_FROM", "").strip()
    if not api_key or not from_addr:
        raise RuntimeError("SENDGRID_API_KEY / GMAIL_FROM が設定されていません。")

    content = [{"type": "text/plain", "value": body_text}]
    if body_html:
        content.append({"type": "text/html", "value": body_html})

    payload = {
        "personalizations": [{"to": [{"email": to_addr}]}],
        "from": {"email": from_addr, "name": "西川純の質問応答システム"},
        "subject": subject,
        "content": content,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    with httpx.Client(timeout=30) as c:
        r = c.post(SENDGRID_URL, headers=headers, json=payload)
        if r.status_code >= 300:
            raise RuntimeError(f"SendGrid送信失敗 {r.status_code}: {r.text[:500]}")
