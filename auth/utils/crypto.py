"""HIT 统一认证密码加密与登录页解析（对齐 IDS encrypt.js）。"""

import base64
import random
import re

from bs4 import BeautifulSoup
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

AES_CHARS = "ABCDEFGHJKMNPQRSTWXYZabcdefhijkmnprstwxyz2345678"


def _random_string(length: int) -> str:
    return "".join(random.choice(AES_CHARS) for _ in range(length))


def encrypt_password(password: str, salt: str | None) -> str:
    """按前端规则 AES 加密密码。"""
    if not salt:
        return password
    try:
        key = salt.encode("utf-8")[:16]
        iv = _random_string(16).encode("utf-8")[:16]
        cipher = AES.new(key, AES.MODE_CBC, iv)
        encrypted = cipher.encrypt(
            pad((_random_string(64) + password).encode("utf-8"), AES.block_size)
        )
        return base64.b64encode(encrypted).decode("utf-8")
    except Exception:
        return password


def parse_login_form(html: str) -> dict:
    """解析 IDS 登录页隐藏字段。"""
    soup = BeautifulSoup(html, "html.parser")
    execution_el = soup.find("input", {"id": "execution"})
    salt_el = soup.find("input", {"id": "pwdEncryptSalt"})
    lt_el = soup.find("input", {"id": "lt"})

    captcha_switch = "2"
    match = re.search(r'var captchaSwitch = "(\d)"', html)
    if match:
        captcha_switch = match.group(1)

    return {
        "execution": execution_el["value"] if execution_el else "",
        "salt": salt_el["value"] if salt_el else None,
        "lt": lt_el["value"] if lt_el else "",
        "captcha_switch": captcha_switch,
    }
