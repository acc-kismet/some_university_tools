"""enroll 项目路径：代码配置 vs 个人 config_dir。"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = PROJECT_ROOT.parent

CONFIG_DIR = PROJECT_ROOT / "config_dir"
CACHE_DIR = CONFIG_DIR / "cache"

USER_CONFIG_FILE = CONFIG_DIR / "myData.jsonc"
USER_CONFIG_EXAMPLE = CONFIG_DIR / "myData.jsonc.example"

SESSION_CACHE_FILE = CACHE_DIR / "session.json"
FINGERPRINT_CACHE_FILE = CACHE_DIR / "browser_fingerprint"

ALL_COURSE_INFO_FILE = CONFIG_DIR / "allCourseInfo.json"
KEY_COURSE_INFO_FILE = CONFIG_DIR / "keyCourseInfo.json"


def ensure_layout() -> None:
    """创建 config_dir 与 cache 目录（个人目录，不提交 git）。"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
