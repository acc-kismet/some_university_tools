"""IDS 浏览器指纹（MULTIFACTOR_BROWSER_FINGERPRINT）。"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

import requests

from auth.logic.constants import AUTH_BASE, IDS_HOST
from auth.utils import http_trace

FINGERPRINT_COOKIE = "MULTIFACTOR_BROWSER_FINGERPRINT"


def _load_cached_fingerprint(cache_path: Path) -> str | None:
    if not cache_path.exists():
        return None
    value = cache_path.read_text(encoding="utf-8").strip()
    return value or None


def get_browser_fingerprint(
    *,
    username: str | None = None,
    cache_path: Path | None = None,
) -> str:
    """获取或生成本机稳定的 32 位大写 MD5 指纹（与 IDS common-header.js 格式一致）。"""
    if cache_path is None:
        raise ValueError("必须指定 fingerprint 缓存路径 cache_path")

    cached = _load_cached_fingerprint(cache_path)
    if cached:
        return cached

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    seed = username or "local"
    fp = hashlib.md5(f"{seed}:{uuid.uuid4()}".encode()).hexdigest().upper()
    cache_path.write_text(fp, encoding="utf-8")
    return fp


def has_fingerprint_cookie(session: requests.Session) -> bool:
    return any(cookie.name == FINGERPRINT_COOKIE for cookie in session.cookies)


def _store_fingerprint_cookie(session: requests.Session, fp: str) -> None:
    for domain, path in (
        ("ids.hit.edu.cn", "/authserver"),
        ("ids.hit.edu.cn", "/"),
        (".hit.edu.cn", "/"),
    ):
        session.cookies.set(FINGERPRINT_COOKIE, fp, domain=domain, path=path)


def ensure_browser_fingerprint(
    session: requests.Session,
    *,
    username: str | None = None,
    referer: str | None = None,
    cache_path: Path | None = None,
) -> str:
    """注册浏览器指纹到 IDS（POST /bfp/info）。"""
    fp = get_browser_fingerprint(username=username, cache_path=cache_path)
    if has_fingerprint_cookie(session):
        return fp

    http_trace.post(
        session,
        "注册浏览器指纹 bfp/info",
        f"{AUTH_BASE}/bfp/info",
        data={"bfp": fp},
        headers={
            "Origin": IDS_HOST,
            "Referer": referer or f"{AUTH_BASE}/login",
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01",
        },
        allow_redirects=True,
        payload={"bfp": fp[:8] + "..."},
        timeout=30,
    )
    if not has_fingerprint_cookie(session):
        _store_fingerprint_cookie(session, fp)
        if http_trace.enabled():
            print(f"  已手动写入 Cookie: {FINGERPRINT_COOKIE}={fp[:8]}...")
    return fp
