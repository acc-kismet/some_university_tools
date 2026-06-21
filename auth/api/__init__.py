"""认证模块对外 API。"""

from auth.logic.flow import LoginError, login, login_or_exit
from auth.logic.target import AuthTarget, resolve_auth_target, start_from_entry
from auth.logic.verify import verify_jw_schedule_api
from auth.utils.session import (
    cookies_to_dict,
    load_session_cache,
    save_session_cache,
    session_from_cookies,
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
