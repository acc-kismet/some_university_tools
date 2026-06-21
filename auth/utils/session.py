"""Session 创建与本地 Cookie 缓存。"""

from __future__ import annotations

import json
from pathlib import Path

import requests

from auth.logic.constants import DEFAULT_HEADERS


def new_session() -> requests.Session:
    """创建带默认请求头的 Session。"""
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    return session


def parse_cookie_string(raw: str) -> dict[str, str]:
    """解析浏览器 Cookie 字符串。"""
    cookies: dict[str, str] = {}
    for part in raw.split(";"):
        part = part.strip()
        if "=" in part:
            key, value = part.split("=", 1)
            cookies[key.strip()] = value.strip()
    return cookies


def cookies_to_dict(session: requests.Session) -> dict[str, str]:
    """导出 Cookie 字典。"""
    return requests.utils.dict_from_cookiejar(session.cookies)


def session_from_cookies(cookies: dict[str, str]) -> requests.Session:
    """从 Cookie 字典创建 Session。"""
    session = new_session()
    session.cookies.update(cookies)
    return session


def save_session_cache(session: requests.Session, path: Path) -> None:
    """保存 Session 到本地 JSON。"""
    path.write_text(
        json.dumps(cookies_to_dict(session), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_session_cache(path: Path) -> requests.Session | None:
    """加载本地 Session；文件不存在或损坏时返回 None。"""
    if not path.exists():
        return None
    try:
        cookies = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return session_from_cookies(cookies) if cookies else None
