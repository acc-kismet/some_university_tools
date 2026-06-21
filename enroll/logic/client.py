"""教务选课客户端。"""

from __future__ import annotations

import json
import time
from copy import deepcopy

import requests

from config import (
    API_ADD_COURSE,
    API_QUERY_COURSES,
    API_QUERY_SEMESTER,
    BASE_FORM,
    COURSE_TYPE_MAP,
    DEFAULT_PAGE_SIZE,
    ENROLL_INTERVAL_SEC,
    MAX_ENROLL_ATTEMPTS,
    REQUEST_TIMEOUT_SEC,
)
from enroll.logic.enroll_result import EnrollResult, parse_enroll_response, timeout_result
from enroll.utils.log import logger
from enroll.utils.paths import ALL_COURSE_INFO_FILE, KEY_COURSE_INFO_FILE


class CourseClient:
    """封装学期查询、课程列表拉取与选课提交。"""

    def __init__(self, session: requests.Session, course_type: str):
        self.session = session
        self.form = deepcopy(BASE_FORM)
        self._set_course_type(course_type)
        self._load_semester()

    def _set_course_type(self, course_type: str) -> None:
        code = COURSE_TYPE_MAP.get(course_type)
        if not code:
            raise ValueError(f"未知选课类型: {course_type}，可选: {list(COURSE_TYPE_MAP)}")
        self.course_type = code
        self.form["p_xkfsdm"] = code
        logger.info("[抢课] 选课类型: %s -> %s", course_type, code)

    def _load_semester(self) -> None:
        query_form = deepcopy(BASE_FORM)
        query_form["p_sfhlctkc"] = 0
        query_form["p_sfhllrlkc"] = 0

        response = self.session.post(API_QUERY_SEMESTER, data=query_form, timeout=REQUEST_TIMEOUT_SEC)
        response.raise_for_status()
        data = response.json()

        self.form.update({
            "p_xn": data["p_xn"],
            "p_xq": data["p_xq"],
            "p_xnxq": data["p_xnxq"],
            "p_dqxn": data["p_dqxn"],
            "p_dqxq": data["p_dqxq"],
            "p_dqxnxq": data["p_dqxnxq"],
        })
        logger.info("[抢课] 当前学期: %s，选课学期: %s", data["p_dqxnxq"], data["p_xnxq"])

    def save_course_info(
        self,
        ignore_conflict: bool = True,
        ignore_zero_capacity: bool = True,
        all_path: str = str(ALL_COURSE_INFO_FILE),
        key_path: str = str(KEY_COURSE_INFO_FILE),
    ) -> None:
        form = self.form.copy()
        form["p_sfhlctkc"] = 1 if ignore_conflict else 0
        form["p_sfhllrlkc"] = 1 if ignore_zero_capacity else 0
        form["pageSize"] = DEFAULT_PAGE_SIZE

        logger.info("[抢课] 正在拉取可选课程列表...")
        probe_response = self.session.post(API_QUERY_COURSES, data=form, timeout=REQUEST_TIMEOUT_SEC)
        probe_response.raise_for_status()
        probe = probe_response.json()
        total = probe["kxrwList"]["total"]
        logger.info("[抢课] 可选课程总数: %d", total)

        form["pageSize"] = total
        all_response = self.session.post(API_QUERY_COURSES, data=form, timeout=REQUEST_TIMEOUT_SEC)
        all_response.raise_for_status()
        all_data = all_response.json()

        with open(all_path, "w", encoding="utf-8") as f:
            json.dump(all_data, f, indent=4, ensure_ascii=False)

        key_list = [
            {
                "课程类型": self.course_type,
                "课程id": item["id"],
                "课程名称": item["kcmc"],
                "授课教师": item["dgjsmc"],
            }
            for item in all_data["kxrwList"]["list"]
        ]
        with open(key_path, "w", encoding="utf-8") as f:
            json.dump(key_list, f, indent=4, ensure_ascii=False)

        logger.info("[抢课] 课程信息已保存: %s, %s", all_path, key_path)

    def enroll_one(self, course_id: str, *, queue_hint: str = "") -> EnrollResult:
        prefix = f"[抢课] {queue_hint} " if queue_hint else "[抢课] "
        form = self.form.copy()
        form["p_id"] = course_id
        form["p_xktjz"] = "rwtjzyx"

        last_result = parse_enroll_response(None, course_id=course_id, attempt=0)
        for attempt in range(1, MAX_ENROLL_ATTEMPTS + 1):
            try:
                response = self.session.post(
                    API_ADD_COURSE,
                    data=form,
                    timeout=REQUEST_TIMEOUT_SEC,
                )
                response.raise_for_status()
                payload = response.json()
                result = parse_enroll_response(payload, course_id=course_id, attempt=attempt)
            except requests.exceptions.Timeout:
                result = timeout_result(course_id=course_id, attempt=attempt)
                logger.error("%s课程 %s 第 %d 次请求超时", prefix, course_id, attempt)
            except requests.RequestException as exc:
                result = parse_enroll_response(
                    {"message": str(exc), "jg": "0"},
                    course_id=course_id,
                    attempt=attempt,
                )
                logger.error("%s课程 %s 第 %d 次请求异常: %s", prefix, course_id, attempt, exc)
            except ValueError as exc:
                result = parse_enroll_response(None, course_id=course_id, attempt=attempt)
                logger.error("%s课程 %s 第 %d 次响应解析失败: %s", prefix, course_id, attempt, exc)

            last_result = result
            logger.info(
                "%s第 %d/%d 次尝试，课程 %s: %s (%s)",
                prefix,
                attempt,
                MAX_ENROLL_ATTEMPTS,
                course_id,
                result.message,
                result.status.value,
            )

            if result.should_stop:
                if result.succeeded:
                    logger.info("%s课程 %s 抢课成功", prefix, course_id)
                elif result.status.value == "already_selected":
                    logger.info("%s课程 %s 已在课表中，跳过", prefix, course_id)
                elif result.status.value == "schedule_conflict":
                    logger.info("%s课程 %s 存在排课冲突，跳过", prefix, course_id)
                return result

            if attempt < MAX_ENROLL_ATTEMPTS:
                logger.info("%s课程 %s 未成功，%d 秒后重试", prefix, course_id, ENROLL_INTERVAL_SEC)
                time.sleep(ENROLL_INTERVAL_SEC)

        logger.warning("%s课程 %s 已达最大重试次数，放弃", prefix, course_id)
        return last_result

    def enroll_many(self, course_ids: list[str] | tuple[str, ...]) -> dict[str, EnrollResult]:
        ids = list(course_ids)
        total = len(ids)
        results: dict[str, EnrollResult] = {}

        for index, course_id in enumerate(ids, start=1):
            remaining = ids[index:]
            if remaining:
                queue_hint = f"[{index}/{total}] 当前 {course_id}，后续: {', '.join(remaining)}"
            else:
                queue_hint = f"[{index}/{total}] 当前 {course_id}（最后一门）"

            logger.info("[抢课] 开始 %s", queue_hint)
            results[course_id] = self.enroll_one(course_id, queue_hint=queue_hint)

        return results

    def get_session(self) -> requests.Session:
        return self.session
