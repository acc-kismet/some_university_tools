"""登录成功后 Session 有效性校验。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

import requests

from auth.logic.constants import JW_SCHEDULE_PROBE_URL
from auth.utils import http_trace

SessionVerifier = Callable[[requests.Session], bool]


def verify_jw_schedule_api(
    session: requests.Session,
    *,
    probe_url: str = JW_SCHEDULE_PROBE_URL,
) -> bool:
    """向课表 JSON 接口 POST 探测：返回数组视为已登录。"""
    try:
        resp = http_trace.post(
            session,
            "探测课表接口 queryrcxxlist",
            probe_url,
            data={"rcrq": datetime.now().strftime("%Y-%m-%d")},
            allow_redirects=True,
            timeout=20,
        )
        return resp.status_code == 200 and isinstance(resp.json(), list)
    except Exception:
        return False


def verify_get_ok(session: requests.Session, url: str) -> bool:
    """GET 指定 URL，2xx 且未跳转到 IDS 登录页视为有效。"""
    try:
        resp = session.get(url, allow_redirects=True, timeout=20)
        if resp.status_code >= 400:
            return False
        if "authserver/login" in resp.url:
            return False
        return True
    except Exception:
        return False


def resolve_verifier(
    verify: SessionVerifier | str | None,
    *,
    service_url: str,
) -> SessionVerifier:
    """构造 Session 校验函数。"""
    if callable(verify):
        return verify
    if isinstance(verify, str):
        url = verify
        return lambda session: verify_get_ok(session, url)
    if "jw.hitsz.edu.cn" in service_url:
        return verify_jw_schedule_api
    return lambda session: verify_get_ok(session, service_url)
