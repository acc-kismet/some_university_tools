"""课表 ICS 入口：python cmd/main.py（在 ics/ 目录下执行）。"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = PROJECT_ROOT.parent
for path in (str(TOOLS_ROOT), str(PROJECT_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from logic.config_loader import load_config
from logic.runner import run_or_exit
from utils.log import setup_logging
from utils.paths import USER_CONFIG_FILE, ensure_layout


def main() -> None:
    ensure_layout()
    config = load_config(USER_CONFIG_FILE)
    setup_logging(level=config.log_level, log_file=config.log_file)
    run_or_exit(config)


if __name__ == "__main__":
    main()
