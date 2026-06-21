"""将日程 JSON 转为 ICS 日历文件。"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

import pytz
from ics import Calendar, Event

from config import LOCATION_PREFIX, TIMEZONE
from utils.log import logger
from utils.paths import OUTPUT_ICS_FILE

TIME_PATTERN = re.compile(r"(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})")


def _parse_event_times(course: dict, tz):
    match = TIME_PATTERN.search(course.get("BT", ""))
    if not match:
        return None

    sh, sm, eh, em = map(int, match.groups())
    day = datetime.strptime(course["SJ"], "%Y-%m-%d")
    begin = tz.localize(day + timedelta(hours=sh, minutes=sm))
    duration = timedelta(hours=eh - sh, minutes=em - sm)
    return begin, duration


def save_as_ics(data: list, output_path: str = str(OUTPUT_ICS_FILE)) -> str:
    logger.info("[课表] 正在将 %d 条原始记录转换为 ICS...", len(data))
    calendar = Calendar()
    tz = pytz.timezone(TIMEZONE)
    skipped = 0
    created = 0

    for course in data:
        parsed = _parse_event_times(course, tz)
        if not parsed:
            logger.warning("跳过无法解析时间的课程: %s", course.get("BT"))
            skipped += 1
            continue

        begin, duration = parsed
        event = Event()
        event.name = course["BT"]
        event.begin = begin
        event.duration = duration

        if course.get("NR"):
            event.location = LOCATION_PREFIX + course["NR"]

        calendar.events.add(event)
        created += 1

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(calendar.serialize())

    logger.info("[课表] 已保存 %s（写入 %d 条，跳过 %d 条）", output_path, created, skipped)
    return output_path
