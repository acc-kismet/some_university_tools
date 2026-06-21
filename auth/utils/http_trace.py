"""HTTP 跳转追踪（AUTH_DEBUG=1 时启用）。"""

from __future__ import annotations

import json
import os
import re
from urllib.parse import parse_qs, urlparse, urljoin

import requests

REDIRECT_CODES = (301, 302, 303, 307, 308)
_step_counter = 0


def enabled() -> bool:
    """是否开启跳转追踪。"""
    return os.environ.get("AUTH_DEBUG", "").lower() in ("1", "true", "yes")


def reset_steps() -> None:
    """重置步骤计数。"""
    global _step_counter
    _step_counter = 0


def _next_label(name: str) -> str:
    global _step_counter
    _step_counter += 1
    return f"[{_step_counter:02d}] {name}"


def describe_page(url: str, body: str = "") -> str:
    """根据 URL/内容推断当前页面类型。"""
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    query = parse_qs(parsed.query)
    lower_body = (body or "")[:800].lower()

    if "reauthloginview" in path or "ismultifactor=true" in parsed.query.lower():
        return "二次认证页 (reAuthLoginView)"
    if host == "jw.hitsz.edu.cn":
        if "ticket" in query:
            return "教务 CAS 回调 (含 ticket)"
        if "session/invalid" in path or "session/invalid" in lower_body:
            return "教务页 (session 无效)"
        return "教务系统 (jw.hitsz.edu.cn)"
    if host == "ids.hit.edu.cn":
        if "/authserver/login" in path:
            if "pwdencryptsalt" in lower_body or "pwdfromid" in lower_body:
                return "IDS 统一认证登录页 (账号密码)"
            return "IDS 统一认证 (/authserver/login)"
        if "/reauthcheck/" in path:
            return "IDS 二次认证接口"
        return "IDS 统一认证平台"
    if "ticket=" in url:
        return "CAS 回调 (含 ticket)"
    return "其他页面"


def _mask_payload(data: dict | None) -> dict | None:
    if data is None:
        return None
    masked = {}
    for key, value in data.items():
        if key in ("password", "dynamicCode", "otpCode"):
            masked[key] = "***"
        else:
            masked[key] = value
    return masked


def _print_response_detail(resp: requests.Response, *, body_preview: bool = True) -> None:
    print(f"  响应: HTTP {resp.status_code}")
    print(f"  当前 URL: {resp.url}")
    print(f"  页面: {describe_page(resp.url, resp.text)}")

    location = resp.headers.get("Location", "")
    if location:
        abs_loc = urljoin(resp.url, location)
        print(f"  跳转 Location: {abs_loc}")
        print(f"  跳转目标: {describe_page(abs_loc)}")

    query = parse_qs(urlparse(resp.url).query)
    if "ticket" in query:
        print(f"  ticket: {query['ticket'][0][:20]}...")

    set_cookie = resp.headers.get("Set-Cookie", "")
    if set_cookie:
        names = re.findall(r"(?:^|,)\s*([^=;\s]+)=", set_cookie)
        if names:
            print(f"  Set-Cookie: {names}")

    if not body_preview:
        return

    text = resp.text.strip()
    if not text:
        print("  响应体: (空)")
        return

    parsed = None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        pass

    if parsed is not None:
        print(f"  响应体(JSON): {json.dumps(parsed, ensure_ascii=False)[:400]}")
    else:
        title = re.search(r"<title[^>]*>([^<]+)</title>", text, re.I)
        if title:
            print(f"  页面标题: {title.group(1).strip()}")
        print(f"  响应体预览: {text[:200]!r}")


def trace_response(step: str, resp: requests.Response, *, payload: dict | None = None) -> None:
    """打印单步响应（不跟随重定向）。"""
    if not enabled():
        return
    print(f"\n[TRACE] {_next_label(step)}")
    if payload is not None:
        print(f"  提交参数: {_mask_payload(payload)}")
    _print_response_detail(resp)


def request(
    session: requests.Session,
    step: str,
    method: str,
    url: str,
    *,
    allow_redirects: bool = True,
    payload: dict | None = None,
    **kwargs,
) -> requests.Response:
    """
    发起 HTTP 请求；DEBUG 模式下逐步打印每一次跳转。
    allow_redirects=False 时只打印首包，不自动跟随。
    """
    if not enabled():
        if method.upper() == "GET":
            return session.get(url, allow_redirects=allow_redirects, **kwargs)
        return session.post(url, allow_redirects=allow_redirects, **kwargs)

    label = _next_label(step)
    print(f"\n[TRACE] {label}")
    print(f"  请求: {method.upper()} {url}")
    if payload is not None:
        print(f"  提交参数: {_mask_payload(payload)}")

    resp = session.request(method.upper(), url, allow_redirects=False, **kwargs)
    _print_response_detail(resp)

    if not allow_redirects:
        return resp

    hop = 0
    while resp.status_code in REDIRECT_CODES:
        location = resp.headers.get("Location", "")
        if not location:
            break
        hop += 1
        next_url = urljoin(resp.url, location)
        follow_method = "GET" if method.upper() == "POST" else method.upper()
        print(f"  --- 跟随重定向 #{hop}: {follow_method} {next_url}")
        resp = session.request(follow_method, next_url, allow_redirects=False, **kwargs)
        _print_response_detail(resp)
        if hop >= 20:
            print("  !!! 重定向次数超过 20，停止跟随")
            break

    return resp


def get(
    session: requests.Session,
    step: str,
    url: str,
    *,
    allow_redirects: bool = True,
    **kwargs,
) -> requests.Response:
    """GET 并追踪跳转。"""
    return request(session, step, "GET", url, allow_redirects=allow_redirects, **kwargs)


def post(
    session: requests.Session,
    step: str,
    url: str,
    *,
    allow_redirects: bool = True,
    payload: dict | None = None,
    **kwargs,
) -> requests.Response:
    """POST 并追踪跳转。"""
    data = kwargs.pop("data", None)
    if payload is None and isinstance(data, dict):
        payload = data
    return request(
        session,
        step,
        "POST",
        url,
        allow_redirects=allow_redirects,
        payload=payload,
        data=data,
        **kwargs,
    )
