"""通过 SMTP 发送 ICS 附件。"""

from __future__ import annotations

import base64
import os
import smtplib
from email import encoders
from email.header import Header
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path

from utils.log import logger
from utils.paths import OUTPUT_ICS_FILE

SMTP_HOST = "smtp.qq.com"
SMTP_PORT = 465


def send_email(ics_path: str = str(OUTPUT_ICS_FILE)) -> None:
    path = Path(ics_path)
    if not path.exists():
        raise FileNotFoundError(f"ICS 文件不存在: {path}")

    mail_user = input("请输入发送邮箱: ").strip()
    mail_pass = input("请输入 SMTP 授权码: ").strip()
    receiver = input("请输入接收邮箱: ").strip()

    if not mail_user or not mail_pass or not receiver:
        raise ValueError("邮箱配置不完整")

    message = MIMEMultipart()
    nickname = "=?utf-8?B?{}?=".format(
        base64.b64encode("课程表".encode("utf-8")).decode("utf-8")
    )
    message["From"] = formataddr((nickname, mail_user))
    message["To"] = formataddr(("收件人", receiver))
    message["Subject"] = Header("课程安排", "utf-8")
    message.attach(MIMEText("学期课程安排见附件", "plain", "utf-8"))

    with path.open("rb") as f:
        part = MIMEBase("text", "calendar", method="REQUEST", name=path.name)
        part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=path.name)
        message.attach(part)

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as smtp:
            smtp.login(mail_user, mail_pass)
            smtp.sendmail(mail_user, [receiver], message.as_string())
        logger.info("[课表] 邮件发送成功: %s -> %s", mail_user, receiver)
    except smtplib.SMTPException as exc:
        logger.error("[课表] 邮件发送失败: %s", exc)
        raise
