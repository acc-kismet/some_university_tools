"""从教务系统按日期范围拉取日程数据。"""

from __future__ import annotations

from datetime import datetime, timedelta

import requests

from config import END_DATE, SCHEDULE_QUERY_URL, START_DATE
from utils.log import logger


def _date_range(start: datetime, end: datetime) -> list[str]:
    dates: list[str] = []
    current = start
    while current <= end:
        dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return dates


def load_data(
    session: requests.Session,
    *,
    start_date: datetime = START_DATE,
    end_date: datetime = END_DATE,
) -> list:
    """逐日 POST 查询日程，合并返回 JSON 数组。"""
    if start_date > end_date:
        raise ValueError(f"开始日期 {start_date.date()} 不能晚于结束日期 {end_date.date()}")

    dates = _date_range(start_date, end_date)
    logger.info(
        "[课表] 准备拉取 %s ~ %s 的日程，共 %d 天",
        dates[0],
        dates[-1],
        len(dates),
    )

    records: list = []
    for index, date in enumerate(dates, start=1):
        logger.info("[课表] 正在获取 %s 的日程 (%d/%d)...", date, index, len(dates))
        response = session.post(SCHEDULE_QUERY_URL, data={"rcrq": date}, timeout=20)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise RuntimeError(f"{date} 接口返回异常: {payload!r}")

        day_count = len(payload)
        records.extend(payload)

        if index < len(dates):
            logger.info(
                "[课表] %s 获取 %d 条，累计 %d 条，下一天: %s",
                date,
                day_count,
                len(records),
                dates[index],
            )
        else:
            logger.info(
                "[课表] %s 获取 %d 条，累计 %d 条（范围结束）",
                date,
                day_count,
                len(records),
            )

    logger.info("[课表] 拉取完成，共 %d 条日程", len(records))
    return records
