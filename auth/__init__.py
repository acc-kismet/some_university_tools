"""IDS 统一认证模块。"""

from auth.api import (
    AuthTarget,
    LoginError,
    cookies_to_dict,
    load_session_cache,
    login,
    login_or_exit,
    resolve_auth_target,
    save_session_cache,
    session_from_cookies,
    start_from_entry,
    verify_jw_schedule_api,
)

__all__ = [
    "AuthTarget",
    "LoginError",
    "login",
    "login_or_exit",
    "resolve_auth_target",
    "start_from_entry",
    "verify_jw_schedule_api",
    "cookies_to_dict",
    "session_from_cookies",
    "save_session_cache",
    "load_session_cache",
]
