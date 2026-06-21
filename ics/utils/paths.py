"""ics 项目路径：代码配置 vs 个人 config_dir。"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = PROJECT_ROOT.parent

CONFIG_DIR = PROJECT_ROOT / "config_dir"
CACHE_DIR = CONFIG_DIR / "cache"

USER_CONFIG_FILE = CONFIG_DIR / "config.jsonc"
USER_CONFIG_EXAMPLE = CONFIG_DIR / "config.jsonc.example"

SESSION_CACHE_FILE = CACHE_DIR / "session.json"
FINGERPRINT_CACHE_FILE = CACHE_DIR / "browser_fingerprint"
OUTPUT_ICS_FILE = CONFIG_DIR / "courses.ics"


def ensure_layout() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
