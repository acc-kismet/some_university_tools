"""抢课入口：python cmd/main.py（在 enroll/ 目录下执行）。"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = PROJECT_ROOT.parent
for path in (str(TOOLS_ROOT), str(PROJECT_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from enroll.logic.config_loader import load_config, validate_credentials
from enroll.logic.runner import run
from enroll.utils.log import setup_logging
from enroll.utils.paths import USER_CONFIG_FILE, ensure_layout


def main() -> None:
    ensure_layout()
    try:
        config = load_config(USER_CONFIG_FILE)
    except FileNotFoundError as exc:
        log = setup_logging()
        log.error("%s", exc)
        log.error("请执行: cp config_dir/myData.jsonc.example config_dir/myData.jsonc")
        sys.exit(1)

    logger = setup_logging(level=config.log_level, log_file=config.log_file)
    try:
        validate_credentials(config)
        run(config)
    except ValueError as exc:
        logger.error("%s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
