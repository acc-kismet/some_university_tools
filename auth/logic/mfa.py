"""IDS 二次验证（MFA）模块。"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from auth.logic.constants import AUTH_BASE, IDS_HOST
from auth.utils import http_trace
from auth.utils.crypto import encrypt_password, parse_login_form
from auth.utils.fingerprint import ensure_browser_fingerprint

MFA_METHODS = {
    "sms": {
        "reauth_type": 3,
        "auth_code_type_name": "reAuthDynamicCodeType",
        "needs_dynamic_code": True,
        "label": "短信验证码",
    },
    "app": {
        "reauth_type": 13,
        "auth_code_type_name": "reAuthWeLinkDynamicCodeType",
        "needs_dynamic_code": True,
        "label": "哈工大APP验证码",
    },
    "email": {
        "reauth_type": 11,
        "auth_code_type_name": "reAuthEmailDynamicCodeType",
        "needs_dynamic_code": True,
        "label": "邮箱验证码",
    },
    "otp": {"reauth_type": 10, "needs_dynamic_code": False, "label": "安全令牌"},
}


class MFAError(Exception):
    """二次验证失败。"""


def is_mfa_url(url: str) -> bool:
    """判断 URL 是否为 MFA 页面。"""
    lower = url.lower()
    return "reauthloginview.do" in lower or "ismultifactor=true" in lower


def is_mfa_page(url: str, body: str) -> bool:
    """判断当前页面是否为 MFA 二次认证页。"""
    if is_mfa_url(url):
        return True
    lower = body.lower()
    return "reauthloginview.do" in lower or "ismultifactor=true" in lower


def reauth_view_url(service: str) -> str:
    """生成 MFA 二次认证页面 URL（供 Referer 等内部请求使用）。"""
    base = f"{AUTH_BASE}/reAuthCheck/reAuthLoginView.do?isMultifactor=true"
    if not service:
        return base
    return f"{base}&service={quote(service, safe='')}"


def parse_mfa_type_ids(html: str) -> list[str]:
    """从 MFA 页面解析可用的认证方式 ID。"""
    soup = BeautifulSoup(html, "html.parser")
    ids: list[str] = []
    seen: set[str] = set()
    for node in soup.select(".changeReAuthTypes"):
        type_id = node.get("id")
        if type_id and type_id not in seen:
            seen.add(type_id)
            ids.append(type_id)
    return ids


def available_mfa_methods(html: str) -> list[dict]:
    """解析页面支持的 MFA 方式列表。"""
    type_ids = parse_mfa_type_ids(html)
    methods = []
    for type_id in type_ids:
        for key, meta in MFA_METHODS.items():
            if str(meta["reauth_type"]) == type_id:
                methods.append({"key": key, **meta})
    return methods


def parse_reauth_params(html: str) -> dict:
    """
    从 MFA 页 inline script 解析 reAuthParams（服务端注入，reAuth.js 读取）。

    关键字段：service, reAuthUserId, reAuthType, isMultifactor, isSleepAccount
    """
    match = re.search(r"var\s+reAuthParams\s*=\s*(\{.*?\})\s*;", html, re.DOTALL)
    if not match:
        return {}
    raw = match.group(1)
    for candidate in (raw, raw.replace("'", '"')):
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue
    return {}


def _reauth_user_id(page_html: str, username: str) -> str:
    """发码接口 userName 应使用页面 reAuthUserId（见 reAuth.js sendDynamicCodeByPhone）。"""
    params = parse_reauth_params(page_html)
    user_id = params.get("reAuthUserId")
    if isinstance(user_id, str) and user_id.strip():
        return user_id.strip()
    return username.strip()


def _post_ids_form(
    session: requests.Session,
    service: str,
    path: str,
    data: dict,
    *,
    as_ajax: bool = False,
    allow_redirects: bool = True,
) -> requests.Response:
    """向 IDS 提交表单请求。"""
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": IDS_HOST,
        "Referer": reauth_view_url(service),
    }
    if as_ajax:
        headers["X-Requested-With"] = "XMLHttpRequest"
        headers["Accept"] = "application/json, text/javascript, */*; q=0.01"
    url = urljoin(AUTH_BASE + "/", path.lstrip("/"))
    step_name = path.strip("/").split("/")[-1] or path
    return http_trace.post(
        session,
        f"MFA POST {step_name}",
        url,
        data=data,
        headers=headers,
        allow_redirects=allow_redirects,
        payload=data,
        timeout=30,
    )


def _parse_json_response(text: str) -> dict | None:
    """尝试解析 JSON 响应体。"""
    text = text.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _is_submit_success(resp: requests.Response) -> bool:
    """判断 reAuthSubmit AJAX 是否成功（与 reAuth.js 一致）。"""
    parsed = _parse_json_response(resp.text)
    if parsed is None:
        return False
    code = str(parsed.get("code", "")).lower()
    if code in ("reauth_failed", "reauth_unauthorized"):
        return False
    if parsed.get("success") is False:
        return False
    return True


def _reached_service(resp: requests.Response, service: str) -> bool:
    """判断 Session 是否已抵达目标站点 service 回调。"""
    if not service:
        return False
    if "ticket=" in resp.url:
        return True
    if resp.url.startswith(service):
        return True
    parsed = urlparse(resp.url)
    if parsed.netloc.endswith("jw.hitsz.edu.cn") and parsed.path.startswith("/authentication/"):
        return True
    return False


def _extract_message(data: dict) -> str:
    """从 JSON 响应提取错误信息。"""
    for key in ("message", "returnMessage", "msg"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "操作失败"


def _ensure_code_sent(resp: requests.Response) -> None:
    """确认验证码发送成功。"""
    if resp.status_code >= 400:
        raise MFAError("发送验证码失败")

    if "/authserver/login" in resp.url.lower():
        raise MFAError("会话已过期，请重新登录")

    parsed = _parse_json_response(resp.text)
    if parsed is None:
        raise MFAError("发送验证码失败")

    if parsed.get("errCode") == "206302":
        raise MFAError("会话已过期，请重新登录")

    if parsed.get("success") is True:
        return
    if str(parsed.get("res", "")).lower() == "success":
        return
    code = parsed.get("code")
    if code in (200, "200"):
        return

    raise MFAError(_extract_message(parsed))


def _fetch_mfa_page_html(session: requests.Session, service: str) -> str:
    """拉取当前 MFA 页 HTML（含最新 reAuthParams）。"""
    resp = http_trace.get(
        session,
        "GET 二次认证页",
        reauth_view_url(service),
        allow_redirects=True,
        timeout=30,
    )
    return resp.text


def change_reauth_type(
    session: requests.Session,
    service: str,
    method: dict,
    *,
    page_html: str = "",
) -> None:
    """切换 MFA 认证方式为短信/APP/邮箱等。"""
    params = parse_reauth_params(page_html)
    is_multifactor = str(params.get("isMultifactor", "true"))
    _post_ids_form(
        session,
        service,
        "/reAuthCheck/changeReAuthType.do",
        {
            "isMultifactor": is_multifactor,
            "reAuthType": str(method["reauth_type"]),
            "service": params.get("service") or service,
        },
        as_ajax=True,
        allow_redirects=True,
    )


def send_mfa_code(
    session: requests.Session,
    service: str,
    username: str,
    method: dict,
    *,
    page_html: str = "",
) -> None:
    """向绑定手机/邮箱发送 MFA 验证码。"""
    if not method.get("needs_dynamic_code"):
        return
    user_id = _reauth_user_id(page_html, username)
    if not user_id:
        raise MFAError("缺少用户名，无法发送验证码")

    resp = _post_ids_form(
        session,
        service,
        "/dynamicCode/getDynamicCodeByReauth.do",
        {
            "userName": user_id,
            "authCodeTypeName": method["auth_code_type_name"],
        },
        as_ajax=True,
        allow_redirects=True,
    )
    _ensure_code_sent(resp)


def _try_follow_cas_redirect(
    session: requests.Session,
    resp: requests.Response,
    service: str,
) -> bool:
    """跟随 CAS 302 到目标站点 service（含 ticket），直至 /authentication/main。"""
    if resp.status_code in (301, 302, 303, 307, 308):
        location = urljoin(resp.url, resp.headers.get("Location", ""))
        if location.startswith(service) or "ticket=" in location:
            final = http_trace.get(
                session,
                "MFA 后跟随 CAS ticket 回调",
                location,
                allow_redirects=True,
                timeout=30,
            )
            return _reached_service(final, service)
        if is_mfa_url(location):
            return False
        final = http_trace.get(
            session, "MFA 后跟随重定向", location, allow_redirects=True, timeout=30
        )
        return _reached_service(final, service)
    return _reached_service(resp, service)


def _fetch_login_form_page(
    session: requests.Session,
    login_url: str,
    service: str,
    step: str,
) -> tuple[dict | None, requests.Response]:
    """
    打开 IDS 登录页并解析表单（不自动跟随重定向，避免误入 MFA 页）。
    若已 302 到目标站点 ticket，返回 (None, resp)。
    """
    from auth.utils.crypto import parse_login_form

    resp = http_trace.get(session, step, login_url, allow_redirects=False, timeout=30)
    if _try_follow_cas_redirect(session, resp, service):
        return None, resp
    if resp.status_code in (301, 302, 303, 307, 308):
        location = urljoin(resp.url, resp.headers.get("Location", ""))
        if is_mfa_url(location):
            raise MFAError(
                "仍停留在二次认证页，验证码提交可能未生效。"
                "请查看 TRACE 中 reAuthSubmit 响应是否为 reAuth_success。"
            )
        raise MFAError(f"无法打开 IDS 登录页，跳转到: {location}")
    if not resp.text or "pwdEncryptSalt" not in resp.text:
        raise MFAError(f"IDS 登录页异常，当前 URL: {resp.url}")
    return parse_login_form(resp.text), resp


def _post_login_password(
    session: requests.Session,
    login_url: str,
    service: str,
    username: str,
    password: str,
    form: dict,
    step: str,
) -> bool:
    """POST 统一认证登录页账号密码，跟随 ticket 回调目标站点。"""
    payload = {
        "username": username,
        "password": encrypt_password(password, form.get("salt")),
        "captcha": "",
        "rememberMe": "true",
        "_eventId": "submit",
        "cllt": "userNameLogin",
        "dllt": "generalLogin",
        "lt": form.get("lt", ""),
        "execution": form.get("execution", ""),
    }
    post = http_trace.post(
        session,
        step,
        login_url,
        data=payload,
        allow_redirects=False,
        payload={"username": username, "password": "***"},
        timeout=30,
    )
    if _try_follow_cas_redirect(session, post, service):
        return True
    location = post.headers.get("Location", "")
    if is_mfa_url(location):
        return False
    return _reached_service(post, service)


def _retry_password_for_ticket(
    session: requests.Session,
    login_url: str,
    service: str,
    username: str,
    password: str,
    log_fn: Callable[[str], None] | None = None,
) -> bool:
    """
    MFA 完成后在 IDS 登录页再次 POST 账号密码（与浏览器点「登录」+ 信任设备一致）。
    """
    if log_fn:
        log_fn("正在 IDS 登录页再次提交账号密码（信任设备后回调目标站点）...")

    form, early = _fetch_login_form_page(
        session, login_url, service, "MFA 后 GET IDS 登录页(第2次密码)"
    )
    if form is None:
        return _reached_service(early, service)

    return _post_login_password(
        session,
        login_url,
        service,
        username,
        password,
        form,
        "第2次 POST 统一认证密码(信任设备后回调目标站点)",
    )


def submit_mfa_code(
    session: requests.Session,
    service: str,
    code: str,
    method: dict,
    *,
    trust_device: bool = True,
    page_html: str = "",
) -> None:
    """提交 MFA 验证码（AJAX），成功后由 finalize 跟随重定向。"""
    if not code.strip():
        raise MFAError("验证码不能为空")

    params = parse_reauth_params(page_html)
    payload = {
        "service": params.get("service") or service,
        "reAuthType": str(method["reauth_type"]),
        "isMultifactor": str(params.get("isMultifactor", "true")),
        "password": "",
        "dynamicCode": code.strip() if method.get("needs_dynamic_code") else "",
        "uuid": "",
        "answer1": "",
        "answer2": "",
        "otpCode": "" if method.get("needs_dynamic_code") else code.strip(),
    }
    if trust_device:
        payload["skipTmpReAuth"] = "true"
    else:
        payload["skipTmpReAuth"] = "false"

    resp = _post_ids_form(
        session,
        service,
        "/reAuthCheck/reAuthSubmit.do",
        payload,
        as_ajax=True,
        allow_redirects=False,
    )
    http_trace.trace_response("MFA reAuthSubmit 提交验证码", resp, payload=payload)

    if not _is_submit_success(resp):
        parsed = _parse_json_response(resp.text)
        if parsed:
            raise MFAError(_extract_message(parsed))
        raise MFAError("二次验证失败，请检查验证码")


def finalize_mfa_login(
    session: requests.Session,
    service: str,
    *,
    username: str | None = None,
    password: str | None = None,
    log_fn: Callable[[str], None] = print,
) -> None:
    """
    MFA 提交成功后的回调（对齐浏览器 reAuth.js）：

    1. reAuthSubmit 返回 reAuth_success（信任此设备）
    2. GET login?service=...（Referer 为二次认证页）-> 302 jw?ticket=...
    3. 跟随 ticket -> https jw -> /authentication/main
    """
    login_url = f"{AUTH_BASE}/login?service={quote(service, safe='')}"
    log_fn(f"[MFA] 验证码已提交，正在回调目标站点: {service}")

    resp = http_trace.get(
        session,
        "MFA 后 GET login?service= (浏览器 window.location)",
        login_url,
        allow_redirects=False,
        headers={"Referer": reauth_view_url(service)},
        timeout=30,
    )

    if _try_follow_cas_redirect(session, resp, service):
        log_fn(f"[MFA] 已通过 ticket 进入目标站点: {service}")
        return

    if resp.status_code in (301, 302, 303, 307, 308):
        location = urljoin(resp.url, resp.headers.get("Location", ""))
        if is_mfa_url(location):
            if username and password and _retry_password_for_ticket(
                session, login_url, service, username, password, log_fn=log_fn
            ):
                return
            raise MFAError(
                "仍停留在二次认证页。"
                "若 TRACE 中 reAuthSubmit 已是 reAuth_success，通常是缺少浏览器指纹 Cookie；"
                "请确认 TRACE 中有「注册浏览器指纹 bfp/info」。"
            )

    if (
        username
        and password
        and resp.status_code == 200
        and resp.text
        and "pwdEncryptSalt" in resp.text
    ):
        log_fn("[MFA] 未直接获得 ticket，尝试在 IDS 登录页再次提交密码")
        form = parse_login_form(resp.text)
        if _post_login_password(
            session,
            login_url,
            service,
            username,
            password,
            form,
            "IDS 登录页 POST 密码(兜底)",
        ):
            return

    resp = http_trace.get(session, "兜底 GET 目标站点 casLogin", service, allow_redirects=True, timeout=30)
    if _reached_service(resp, service):
        return

    raise MFAError(
        f"无法回调目标站点，最终 URL: {resp.url}。"
        "请用 AUTH_DEBUG=1 查看 GET login?service= 的 Location 是否为 jw?ticket=..."
    )


def complete_mfa_terminal(
    session: requests.Session,
    service: str,
    username: str,
    page_html: str,
    *,
    mfa_method: str = "sms",
    password: str | None = None,
    trust_device: bool = True,
    fingerprint_cache_path: Path,
    input_fn: Callable[[str], str] = input,
    log_fn: Callable[[str], None] = print,
) -> None:
    """终端交互完成二次验证。"""
    methods = available_mfa_methods(page_html)
    if not methods:
        refreshed = http_trace.get(
            session,
            "刷新二次认证页",
            reauth_view_url(service),
            allow_redirects=True,
            timeout=30,
        )
        page_html = refreshed.text
        methods = available_mfa_methods(page_html)

    if not methods:
        raise MFAError("未找到可用的二次认证方式")

    method = next((m for m in methods if m["key"] == mfa_method), None)
    if method is None:
        keys = ", ".join(m["key"] for m in methods)
        raise MFAError(f"不支持 {mfa_method}，可用方式: {keys}")

    ensure_browser_fingerprint(
        session,
        username=username,
        referer=reauth_view_url(service),
        cache_path=fingerprint_cache_path,
    )

    log_fn(f"[MFA] 二次认证方式: {method['label']} ({method['key']})")
    log_fn(f"[MFA] 目标回调: {service}")

    params = parse_reauth_params(page_html)
    current_type = str(params.get("reAuthType", ""))
    if current_type != str(method["reauth_type"]):
        change_reauth_type(session, service, method, page_html=page_html)
        page_html = _fetch_mfa_page_html(session, service)

    if method["needs_dynamic_code"]:
        log_fn(f"[MFA] 正在通过 {method['label']} 向绑定账号发送验证码...")
        send_mfa_code(session, service, username, method, page_html=page_html)
        log_fn("[MFA] 验证码已发送，请在终端输入")
        page_html = _fetch_mfa_page_html(session, service)

    if trust_device:
        log_fn("[MFA] 将勾选「信任此设备」")
    code = input_fn("请输入二次验证码: ").strip()

    log_fn("[MFA] 正在提交验证码...")
    submit_mfa_code(
        session,
        service,
        code,
        method,
        trust_device=trust_device,
        page_html=page_html,
    )
    finalize_mfa_login(
        session, service, username=username, password=password, log_fn=log_fn
    )
    log_fn(f"[MFA] 二次验证完成，已进入目标站点: {service}")
