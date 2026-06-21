"""IDS 统一认证登录主流程。"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from auth.logic.mfa import (
    MFAError,
    complete_mfa_terminal,
    is_mfa_page,
    is_mfa_url,
    reauth_view_url,
)
from auth.logic.target import AuthTarget, resolve_auth_target, start_from_entry
from auth.logic.verify import SessionVerifier, resolve_verifier
from auth.utils import http_trace
from auth.utils.crypto import encrypt_password, parse_login_form
from auth.utils.fingerprint import ensure_browser_fingerprint
from auth.utils.session import (
    load_session_cache,
    new_session,
    parse_cookie_string,
    save_session_cache,
    session_from_cookies,
)
from auth.utils.log import log_step, logger, setup_logging


class LoginError(Exception):
    """登录失败。"""


def _submit_password_login(
    session: requests.Session,
    login_url: str,
    username: str,
    password: str,
    form: dict,
) -> requests.Response:
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
    safe_payload = {
        "username": username,
        "password": "***",
        "execution": (form.get("execution") or "")[:8] + "...",
    }
    return http_trace.post(
        session,
        "第1次 POST 统一认证密码",
        login_url,
        data=payload,
        allow_redirects=False,
        payload=safe_payload,
        timeout=30,
    )


def _parse_login_error(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    tip = soup.find(id="showErrorTip")
    return tip.get_text(strip=True) if tip else ""


def _fetch_mfa_html(
    session: requests.Session,
    service: str,
    redirect_location: str = "",
) -> str:
    if redirect_location:
        resp = http_trace.get(
            session, "302 进入二次认证页", redirect_location, allow_redirects=True, timeout=30
        )
        if is_mfa_page(resp.url, resp.text):
            return resp.text
    resp = http_trace.get(
        session,
        "GET 二次认证页 reAuthLoginView",
        reauth_view_url(service),
        allow_redirects=True,
        timeout=30,
    )
    return resp.text


def _cache_paths(cache_dir: Path) -> tuple[Path, Path]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "session.json", cache_dir / "browser_fingerprint"


def _run_mfa(
    session: requests.Session,
    service: str,
    username: str,
    password: str,
    page_html: str,
    *,
    mfa_method: str,
    trust_device: bool,
    fingerprint_cache_path: Path,
    input_fn: Callable[[str], str],
    log_fn: Callable[[str], None],
) -> requests.Session:
    try:
        complete_mfa_terminal(
            session,
            service,
            username,
            page_html,
            mfa_method=mfa_method,
            password=password,
            trust_device=trust_device,
            fingerprint_cache_path=fingerprint_cache_path,
            input_fn=input_fn,
            log_fn=log_fn,
        )
    except MFAError as exc:
        raise LoginError(str(exc)) from exc
    return session


def _open_browser_for_slider(
    login_url: str,
    username: str,
    password: str,
    input_fn: Callable[[str], str],
    log_fn: Callable[[str], None],
) -> requests.Session:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise LoginError(
            "需要滑块验证，请安装 playwright: pip install playwright && playwright install chromium"
        ) from exc

    log_fn("[认证] 正在打开浏览器，请完成滑块并点击登录...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(login_url, wait_until="domcontentloaded")
        if page.locator("#username").count():
            page.fill("#username", username)
        if page.locator("#password").count():
            page.fill("#password", password)
        input_fn("请在浏览器完成滑块并点击登录，出现二次认证页后回终端按回车...")
        cookies = context.cookies()
        browser.close()

    session = new_session()
    for item in cookies:
        session.cookies.set(item["name"], item["value"], domain=item.get("domain"))
    return session


def _finalize_login(
    session: requests.Session,
    target: AuthTarget,
    verifier: SessionVerifier,
    *,
    save_session: bool,
    session_cache_path: Path,
    log_fn: Callable[[str], None],
) -> requests.Session:
    if not verifier(session):
        log_fn(f"[认证] 正在验证目标站点 Session: {target.service_url}")
        http_trace.get(
            session,
            "兜底 GET 目标 service",
            target.service_url,
            allow_redirects=True,
            timeout=30,
        )
    if not verifier(session):
        raise LoginError("登录未完成，目标站点 Session 仍不可用")

    if save_session:
        save_session_cache(session, session_cache_path)
    log_fn(f"[认证] 登录成功，目标站点 Session 可用: {target.service_url}")
    if save_session:
        log_fn(f"[认证] Session 已缓存到 {session_cache_path}")
    return session


def login(
    username: str,
    password: str,
    entry_url: str,
    *,
    cache_dir: Path,
    verify: SessionVerifier | str | None = None,
    mfa_method: str = "sms",
    trust_device: bool = True,
    use_session_cache: bool = True,
    save_session: bool = True,
    input_fn: Callable[[str], str] = input,
    log_fn: Callable[[str], None] = log_step,
) -> requests.Session:
    """
    通过 IDS 统一认证登录，并返回已写入 Cookie 的 Session。

    cache_dir: 登录缓存目录（session.json / browser_fingerprint）。
    entry_url: 目标站点入口，未登录时会 302 到 IDS。
    """
    session_cache_path, fingerprint_cache_path = _cache_paths(cache_dir)
    target = resolve_auth_target(entry_url)
    verifier = resolve_verifier(verify, service_url=target.service_url)
    setup_logging()

    log_fn(f"[认证] 开始登录，目标站点: {target.entry_url}")
    log_fn(f"[认证] CAS service: {target.service_url}")

    http_trace.reset_steps()
    if http_trace.enabled():
        print("\n========== 登录跳转追踪 (AUTH_DEBUG=1) ==========")

    if use_session_cache:
        log_fn(f"[认证] 检查 Session 缓存: {session_cache_path}")
        cached = load_session_cache(session_cache_path)
        if cached and verifier(cached):
            log_fn("[认证] Session 缓存有效，跳过登录")
            return cached
        log_fn("[认证] Session 缓存无效或不存在，执行完整登录")

    session = new_session()
    log_fn(f"[认证] 步骤 1/4: 访问目标站点入口 → IDS ({target.entry_url})")
    resolved_login_url = start_from_entry(session, target)
    log_fn(f"[认证] 步骤 2/4: 加载 IDS 登录页")
    page = http_trace.get(
        session, "GET IDS 登录页", resolved_login_url, allow_redirects=True, timeout=30
    )
    log_fn("[认证] 步骤 3/4: 注册浏览器指纹")
    ensure_browser_fingerprint(
        session, username=username, referer=page.url, cache_path=fingerprint_cache_path
    )
    form = parse_login_form(page.text)
    log_fn(f"[认证] 步骤 4/4: 提交账号 {username} 的密码")
    post_resp = _submit_password_login(session, resolved_login_url, username, password, form)
    service = target.service_url

    if post_resp.status_code in (301, 302, 303, 307, 308):
        location = post_resp.headers.get("Location", "")
        if location.startswith(service) or "ticket=" in location:
            log_fn("[认证] 密码已通过，正在跟随 ticket 进入目标站点")
            http_trace.get(
                session, "已登录，跟随 ticket 回调目标站点", location, allow_redirects=True, timeout=30
            )
            return _finalize_login(
                session, target, verifier,
                save_session=save_session,
                session_cache_path=session_cache_path,
                log_fn=log_fn,
            )
        if is_mfa_url(location):
            log_fn("[认证] 密码验证通过，进入二次认证 (MFA)")
            mfa_html = _fetch_mfa_html(session, service, location)
            session = _run_mfa(
                session, service, username, password, mfa_html,
                mfa_method=mfa_method, trust_device=trust_device,
                fingerprint_cache_path=fingerprint_cache_path,
                input_fn=input_fn, log_fn=log_fn,
            )
            return _finalize_login(
                session, target, verifier,
                save_session=save_session,
                session_cache_path=session_cache_path,
                log_fn=log_fn,
            )

    if is_mfa_page(post_resp.url, post_resp.text):
        log_fn("[认证] 密码验证通过，进入二次认证 (MFA)")
        session = _run_mfa(
            session, service, username, password, post_resp.text,
            mfa_method=mfa_method, trust_device=trust_device,
            fingerprint_cache_path=fingerprint_cache_path,
            input_fn=input_fn, log_fn=log_fn,
        )
        return _finalize_login(
            session, target, verifier,
            save_session=save_session,
            session_cache_path=session_cache_path,
            log_fn=log_fn,
        )

    error = _parse_login_error(post_resp.text)
    need_slider = "动态码" in error or "图形" in error or "验证码" in error
    if need_slider and post_resp.status_code not in (301, 302, 303, 307, 308):
        log_fn(f"[认证] 需要滑块/图形验证（{error or 'captcha_switch=2'}），请在浏览器完成")
        session = _open_browser_for_slider(resolved_login_url, username, password, input_fn, log_fn)
        mfa_html = _fetch_mfa_html(session, service)
        if is_mfa_page(reauth_view_url(service), mfa_html):
            log_fn("[认证] 滑块完成后检测到二次认证 (MFA)")
            session = _run_mfa(
                session, service, username, password, mfa_html,
                mfa_method=mfa_method, trust_device=trust_device,
                fingerprint_cache_path=fingerprint_cache_path,
                input_fn=input_fn, log_fn=log_fn,
            )
        elif not verifier(session):
            raise LoginError("滑块后未进入二次认证，且目标站点 Session 不可用")
        return _finalize_login(
            session, target, verifier,
            save_session=save_session,
            session_cache_path=session_cache_path,
            log_fn=log_fn,
        )

    raise LoginError(error or "登录失败")


def login_or_exit(username: str, password: str, entry_url: str, **kwargs) -> requests.Session:
    try:
        return login(username, password, entry_url, **kwargs)
    except LoginError as exc:
        setup_logging()
        logger.error("[认证] 登录失败: %s", exc)
        sys.exit(1)
