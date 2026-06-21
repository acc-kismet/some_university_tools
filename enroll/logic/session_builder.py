"""构建已登录 Session。"""

from __future__ import annotations

import sys

import requests

from auth.api import LoginError, login, session_from_cookies
from config import ENTRY_URL
from enroll.logic.config_loader import EnrollConfig
from enroll.utils.log import logger
from enroll.utils.paths import CACHE_DIR


def build_session(config: EnrollConfig) -> requests.Session:
    if config.uses_cookie_login:
        logger.info("[抢课] 使用配置文件中的 Cookie，跳过 IDS 登录")
        return session_from_cookies(config.cookies)

    logger.info("[抢课] 准备登录教务系统，入口: %s", ENTRY_URL)
    try:
        return login(
            config.username,
            config.password,
            ENTRY_URL,
            cache_dir=CACHE_DIR,
            mfa_method=config.mfa_method,
            trust_device=config.trust_device,
            use_session_cache=config.use_session_cache,
            save_session=config.save_session,
            log_fn=logger.info,
        )
    except LoginError as exc:
        logger.error("[抢课] 登录失败: %s", exc)
        sys.exit(1)
