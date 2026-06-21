"""myData.jsonc 加载与运行模式判定。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from enroll.utils.log import logger
from enroll.utils.paths import USER_CONFIG_FILE

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
PLACEHOLDER_COURSE_IDS = frozenset({"", "需要抢的课程id"})
COURSE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


class RunMode(Enum):
    EXPORT_COURSES = "export_courses"
    ENROLL = "enroll"


@dataclass(frozen=True)
class EnrollConfig:
    username: str
    password: str
    course_type: str
    course_ids: tuple[str, ...]
    run_mode: RunMode
    mfa_method: str
    trust_device: bool
    use_session_cache: bool
    save_session: bool
    cookies: dict[str, str]
    log_level: str | None = None
    log_file: str | None = None

    @property
    def uses_cookie_login(self) -> bool:
        return bool(self.cookies)


def _normalize_course_ids(raw_ids) -> tuple[str, ...]:
    if not isinstance(raw_ids, list):
        return ()
    ids: list[str] = []
    seen: set[str] = set()
    for item in raw_ids:
        course_id = str(item).strip()
        if not course_id or course_id in PLACEHOLDER_COURSE_IDS:
            continue
        if course_id in seen:
            logger.warning("忽略重复课程 ID: %s", course_id)
            continue
        if not COURSE_ID_PATTERN.fullmatch(course_id):
            logger.warning("忽略非法课程 ID: %s", course_id)
            continue
        seen.add(course_id)
        ids.append(course_id)
    return tuple(ids)


def resolve_run_mode(data: dict, course_ids: tuple[str, ...]) -> RunMode:
    explicit = str(data.get("runMode", "auto")).strip().lower()
    if explicit == "export":
        return RunMode.EXPORT_COURSES
    if explicit == "enroll":
        if not course_ids:
            raise ValueError("runMode=enroll 时必须配置有效的 selectedCourseIds")
        return RunMode.ENROLL
    if explicit == "auto":
        return RunMode.ENROLL if course_ids else RunMode.EXPORT_COURSES
    raise ValueError(f"未知 runMode: {explicit}，可选: auto / enroll / export")


def load_config(path: str | Path = USER_CONFIG_FILE) -> EnrollConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    data = _load_jsonc(config_path)

    course_ids = _normalize_course_ids(data.get("selectedCourseIds", []))
    run_mode = resolve_run_mode(data, course_ids)
    cookies = data.get("cookies") or {}
    if not isinstance(cookies, dict):
        cookies = {}

    return EnrollConfig(
        username=str(data.get("username", "")).strip(),
        password=str(data.get("password", "")).strip(),
        course_type=str(data.get("courseType", "")).strip(),
        course_ids=course_ids,
        run_mode=run_mode,
        mfa_method=str(data.get("mfaMethod", "sms")),
        trust_device=bool(data.get("trustDevice", True)),
        use_session_cache=bool(data.get("useSessionCache", True)),
        save_session=bool(data.get("saveSession", True)),
        cookies={str(k): str(v) for k, v in cookies.items()},
        log_level=data.get("logLevel"),
        log_file=data.get("logFile"),
    )


def validate_credentials(config: EnrollConfig) -> None:
    if config.uses_cookie_login:
        return
    if config.username in PLACEHOLDER_USERNAMES or config.password in PLACEHOLDER_PASSWORDS:
        raise ValueError(
            f"请在 {USER_CONFIG_FILE} 中填写有效的 username / password，或提供 cookies"
        )
    if config.run_mode == RunMode.ENROLL and not config.course_type:
        raise ValueError("抢课模式需要配置 courseType")
