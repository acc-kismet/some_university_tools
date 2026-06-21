"""config.jsonc 加载与校验。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from getpass import getpass
from pathlib import Path

from utils.log import logger
from utils.paths import USER_CONFIG_FILE

# 去掉 // 与 /* */ 注释（字符串内的 / 不处理）
_JSONC_COMMENT_RE = re.compile(
    r'("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')|//[^\n]*|/\*.*?\*/',
    re.DOTALL,
)


def _load_jsonc(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    stripped = _JSONC_COMMENT_RE.sub(
        lambda m: m.group(1) if m.group(1) else "",
        raw,
    )
    return json.loads(stripped)

CONFIG_FILE = USER_CONFIG_FILE.name
PLACEHOLDER_USERNAMES = frozenset({"", "账号", "你的学号"})
PLACEHOLDER_PASSWORDS = frozenset({"", "密码", "你的密码"})


class MailAction(Enum):
    SKIP = "skip"
    SEND = "send"
    PROMPT = "prompt"


@dataclass(frozen=True)
class IcsConfig:
    username: str
    password: str
    mfa_method: str
    trust_device: bool
    use_session_cache: bool
    save_session: bool
    send_mail: MailAction
    log_level: str | None = None
    log_file: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None


def _parse_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    return datetime.strptime(raw.strip(), "%Y-%m-%d")


def _resolve_mail_action(raw) -> MailAction:
    if raw is True:
        return MailAction.SEND
    if raw is False:
        return MailAction.SKIP
    value = str(raw or "prompt").strip().lower()
    if value in {"y", "yes", "true", "send", "1"}:
        return MailAction.SEND
    if value in {"n", "no", "false", "skip", "0"}:
        return MailAction.SKIP
    return MailAction.PROMPT


def load_config(path: str | Path = USER_CONFIG_FILE) -> IcsConfig:
    config_path = Path(path)
    data: dict = {}
    if config_path.exists():
        data = _load_jsonc(config_path)
    else:
        logger.warning("未找到 %s，将使用交互式输入", config_path.name)

    return IcsConfig(
        username=str(data.get("username", "")).strip(),
        password=str(data.get("password", "")).strip(),
        mfa_method=str(data.get("mfaMethod", "sms")),
        trust_device=bool(data.get("trustDevice", True)),
        use_session_cache=bool(data.get("useSessionCache", True)),
        save_session=bool(data.get("saveSession", True)),
        send_mail=_resolve_mail_action(data.get("sendMail", "prompt")),
        log_level=data.get("logLevel"),
        log_file=data.get("logFile"),
        start_date=_parse_date(data.get("startDate")),
        end_date=_parse_date(data.get("endDate")),
    )


def resolve_credentials(config: IcsConfig) -> tuple[str, str]:
    username = config.username
    password = config.password

    if not username or username in PLACEHOLDER_USERNAMES:
        username = input("请输入学号: ").strip()
    if not password or password in PLACEHOLDER_PASSWORDS:
        password = getpass("请输入密码: ")

    if not username or not password:
        raise ValueError("学号或密码不能为空")

    return username, password
