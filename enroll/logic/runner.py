"""抢课流程编排。"""

from __future__ import annotations

from dataclasses import dataclass

from enroll.logic.client import CourseClient
from enroll.logic.config_loader import EnrollConfig, RunMode
from enroll.logic.enroll_result import EnrollResult, EnrollStatus
from enroll.logic.session_builder import build_session
from enroll.utils.log import logger


@dataclass(frozen=True)
class EnrollSummary:
    succeeded: tuple[str, ...]
    skipped: tuple[str, ...]
    failed: tuple[str, ...]

    @property
    def total(self) -> int:
        return len(self.succeeded) + len(self.skipped) + len(self.failed)


def _format_queue(course_ids: tuple[str, ...]) -> str:
    return " → ".join(course_ids)


def run(config: EnrollConfig) -> EnrollSummary | None:
    session = build_session(config)
    client = CourseClient(session, config.course_type)

    if config.run_mode is RunMode.EXPORT_COURSES:
        logger.info("[抢课] 运行模式: 导出课程列表（类型: %s）", config.course_type)
        client.save_course_info()
        return None

    logger.info(
        "[抢课] 运行模式: 抢课，共 %d 门，队列: %s",
        len(config.course_ids),
        _format_queue(config.course_ids),
    )
    results = client.enroll_many(config.course_ids)
    summary = _summarize(results)
    _log_summary(summary, config.course_ids)
    return summary


def _summarize(results: dict[str, EnrollResult]) -> EnrollSummary:
    succeeded: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []

    for course_id, result in results.items():
        if result.status is EnrollStatus.SUCCESS:
            succeeded.append(course_id)
        elif result.should_stop:
            skipped.append(course_id)
        else:
            failed.append(course_id)

    return EnrollSummary(tuple(succeeded), tuple(skipped), tuple(failed))


def _log_summary(summary: EnrollSummary, course_ids: tuple[str, ...]) -> None:
    logger.info(
        "[抢课] 全部完成 (%d 门): 成功 %d，跳过 %d，失败 %d",
        len(course_ids),
        len(summary.succeeded),
        len(summary.skipped),
        len(summary.failed),
    )
    if summary.succeeded:
        logger.info("[抢课] 成功: %s", ", ".join(summary.succeeded))
    if summary.skipped:
        logger.info("[抢课] 跳过: %s", ", ".join(summary.skipped))
    if summary.failed:
        logger.warning("[抢课] 失败: %s", ", ".join(summary.failed))
