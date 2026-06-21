"""解析目标站点 URL 与 CAS service，并从入口触发 IDS 重定向。"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote, urlparse

import requests

from auth.logic.constants import AUTH_BASE
from auth.utils import http_trace


@dataclass(frozen=True)
class AuthTarget:
    """一次 CAS 登录所绑定的目标站点。"""

    entry_url: str
    service_url: str
    ids_login_url: str


def resolve_auth_target(url: str) -> AuthTarget:
    """
    解析目标站点入口 URL。

    示例：`http://jw.hitsz.edu.cn/casLogin`
    未登录时访问该地址会 302 到 IDS，CAS service 即此 URL。
    """
    raw = url.strip()
    if not raw:
        raise ValueError("entry_url 不能为空")

    parsed = urlparse(raw)
    if "ids.hit.edu.cn" in parsed.netloc.lower():
        raise ValueError(
            "entry_url 应为目标站点入口（如 http://jw.hitsz.edu.cn/casLogin），"
            "不要传入 IDS 登录页 URL"
        )

    return AuthTarget(
        entry_url=raw,
        service_url=raw,
        ids_login_url=f"{AUTH_BASE}/login?service={quote(raw, safe='')}",
    )


def start_from_entry(session: requests.Session, target: AuthTarget) -> str:
    """从目标站点入口进入统一认证，返回 IDS 登录页 URL。"""
    resp = http_trace.get(
        session,
        "访问目标站点入口",
        target.entry_url,
        allow_redirects=True,
        timeout=30,
    )
    if "authserver/login" in resp.url:
        return resp.url
    return target.ids_login_url
