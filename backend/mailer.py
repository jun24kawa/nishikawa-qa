# -*- coding: utf-8 -*-
r"""
確認メールの送信（Gmail SMTP、アプリパスワード）。

`メール設定.ps1`（PC月次点検の通知メール）と同じ仕組みを使い回す。
違いは、パスワードをDPAPIではなく環境変数（Renderのダッシュボードで設定）から読む点。

環境変数：
  GMAIL_FROM       … 送信元のGmailアドレス
  GMAIL_APP_PASSWORD … Googleの「アプリパスワード」（16文字、スペースは有無どちらでも可）
"""
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587


def send_mail(to_addr: str, subject: str, body_text: str, body_html: str = "") -> None:
    from_addr = os.environ.get("GMAIL_FROM", "").strip()
    app_password = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()
    if not from_addr or not app_password:
        raise RuntimeError("GMAIL_FROM / GMAIL_APP_PASSWORD が設定されていません。")

    if body_html:
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(body_text, "plain", "utf-8"))
        msg.attach(MIMEText(body_html, "html", "utf-8"))
    else:
        msg = MIMEText(body_text, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = formataddr(("西川純の質問応答システム", from_addr))
    msg["To"] = to_addr

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30) as server:
        server.starttls()
        server.login(from_addr, app_password)
        server.sendmail(from_addr, [to_addr], msg.as_string())
