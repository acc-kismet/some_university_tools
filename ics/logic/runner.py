"""ICS 生成流程编排。"""

from __future__ import annotations

import sys

from auth.api import login_or_exit
from config import END_DATE, ENTRY_URL, START_DATE
from logic.config_loader import IcsConfig, MailAction, resolve_credentials
from logic.load_data import load_data
from logic.save_as_ics import save_as_ics
from logic.send_email import send_email
from utils.log import logger
from utils.paths import CACHE_DIR, OUTPUT_ICS_FILE


def run(config: IcsConfig) -> None:
    username, password = resolve_credentials(config)

    start_date = config.start_date or START_DATE
    end_date = config.end_date or END_DATE

    logger.info("[课表] 步骤 1/3: 登录教务系统 (入口: %s)", ENTRY_URL)
    session = login_or_exit(
        username,
        password,
        ENTRY_URL,
        cache_dir=CACHE_DIR,
        mfa_method=config.mfa_method,
        trust_device=config.trust_device,
        use_session_cache=config.use_session_cache,
        save_session=config.save_session,
        log_fn=logger.info,
    )

    logger.info(
        "[课表] 步骤 2/3: 拉取日程 %s ~ %s",
        start_date.strftime("%Y-%m-%d"),
        end_date.strftime("%Y-%m-%d"),
    )
    records = load_data(session, start_date=start_date, end_date=end_date)

    logger.info("[课表] 步骤 3/3: 生成 ICS 文件 %s", OUTPUT_ICS_FILE)
    output_path = save_as_ics(records, str(OUTPUT_ICS_FILE))
    _handle_mail(config.send_mail, output_path)


def _handle_mail(action: MailAction, output_path: str) -> None:
    if action is MailAction.SEND:
        logger.info("[课表] 正在发送邮件，附件: %s", output_path)
        send_email(output_path)
        return
    if action is MailAction.SKIP:
        logger.info("[课表] 已生成 %s，跳过邮件", output_path)
        return

    if input("是否邮件发送？(y/n): ").strip().lower() == "y":
        logger.info("[课表] 正在发送邮件，附件: %s", output_path)
        send_email(output_path)
    else:
        logger.info("[课表] 已生成 %s，跳过邮件", output_path)


def run_or_exit(config: IcsConfig) -> None:
    try:
        run(config)
    except (RuntimeError, ValueError) as exc:
        logger.error("[课表] %s", exc)
        sys.exit(1)
