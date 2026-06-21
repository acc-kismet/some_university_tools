"""选课接口响应解析。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class EnrollStatus(Enum):
    SUCCESS = "success"
    ALREADY_SELECTED = "already_selected"
    SCHEDULE_CONFLICT = "schedule_conflict"
    FAILED = "failed"
    TIMEOUT = "timeout"
    INVALID_RESPONSE = "invalid_response"


@dataclass(frozen=True)
class EnrollResult:
    status: EnrollStatus
    message: str
    course_id: str
    attempt: int
    jg: str | None = None

    @property
    def should_stop(self) -> bool:
        return self.status in {
            EnrollStatus.SUCCESS,
            EnrollStatus.ALREADY_SELECTED,
            EnrollStatus.SCHEDULE_CONFLICT,
        }

    @property
    def succeeded(self) -> bool:
        return self.status == EnrollStatus.SUCCESS


# 接口 jg=1 表示业务成功；其余已知文案按完整匹配归类。
_JG_SUCCESS = {"1", 1, True}
_STOP_MESSAGES: dict[str, EnrollStatus] = {
    "操作成功": EnrollStatus.SUCCESS,
    "该任务已选择": EnrollStatus.ALREADY_SELECTED,
}
_CONFLICT_PATTERNS = (
    re.compile(r"^与.+冲突$"),
    re.compile(r"^该课程与.+冲突$"),
    re.compile(r"^排课冲突[:：]?"),
    re.compile(r"^时间冲突[:：]?"),
)


def _normalize(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _match_conflict(message: str) -> bool:
    if not message:
        return False
    if message == "冲突":
        return True
    return any(pattern.search(message) for pattern in _CONFLICT_PATTERNS)


def parse_enroll_response(payload: dict | None, *, course_id: str, attempt: int) -> EnrollResult:
    """解析 addGouwuche 响应，优先使用 jg 字段，其次匹配已知 message。"""
    if not isinstance(payload, dict):
        return EnrollResult(
            EnrollStatus.INVALID_RESPONSE,
            "响应不是 JSON 对象",
            course_id,
            attempt,
        )

    jg = _normalize(payload.get("jg"))
    message = _normalize(payload.get("message"))

    if payload.get("jg") in _JG_SUCCESS or jg == "1":
        return EnrollResult(EnrollStatus.SUCCESS, message or "操作成功", course_id, attempt, jg)

    if message in _STOP_MESSAGES:
        return EnrollResult(_STOP_MESSAGES[message], message, course_id, attempt, jg)

    if _match_conflict(message):
        return EnrollResult(EnrollStatus.SCHEDULE_CONFLICT, message, course_id, attempt, jg)

    return EnrollResult(EnrollStatus.FAILED, message or "选课失败", course_id, attempt, jg)


def timeout_result(*, course_id: str, attempt: int) -> EnrollResult:
    return EnrollResult(EnrollStatus.TIMEOUT, "请求超时", course_id, attempt)
