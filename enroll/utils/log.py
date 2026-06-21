"""控制台与文件日志。"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path


class ColoredFormatter(logging.Formatter):
    COLOR_CODES = {
        "DEBUG": "\033[94m",
        "INFO": "\033[92m",
        "WARNING": "\033[93m",
        "ERROR": "\033[91m",
        "CRITICAL": "\033[95m",
        "RESET": "\033[0m",
    }

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        if not sys.stderr.isatty():
            return message
        color = self.COLOR_CODES.get(record.levelname, self.COLOR_CODES["RESET"])
        return f"{color}{message}{self.COLOR_CODES['RESET']}"


def _parse_level(raw: str | None, default: str = "INFO") -> int:
    name = (raw or default).strip().upper()
    return getattr(logging, name, logging.INFO)


def setup_logging(
    name: str = "enroll",
    *,
    level: str | None = None,
    log_file: str | Path | None = None,
) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    resolved_level = _parse_level(level or os.environ.get("ENROLL_LOG_LEVEL") or os.environ.get("LOG_LEVEL"))
    logger.setLevel(resolved_level)
    logger.propagate = False

    formatter = ColoredFormatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(resolved_level)
    logger.addHandler(stream_handler)

    file_path = log_file or os.environ.get("ENROLL_LOG_FILE")
    if file_path:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(path, encoding="utf-8")
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        file_handler.setLevel(resolved_level)
        logger.addHandler(file_handler)

    return logger


logger = logging.getLogger("enroll")
