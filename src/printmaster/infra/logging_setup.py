"""Registro rotativo con ocultamiento de claves de API."""

from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

from printmaster.infra import paths

_PATTERNS = [
    (re.compile(r"(api[_-]?key\s*[=:]\s*)\S+", re.IGNORECASE), r"\1***"),
    (re.compile(r"AIza[0-9A-Za-z_\-]{35}"), "***"),
]


def redact(text: str) -> str:
    for pattern, repl in _PATTERNS:
        text = pattern.sub(repl, text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = None
        return True


def setup_logging(log_dir: Path | None = None) -> logging.Logger:
    log_dir = log_dir or (paths.data_dir() / "logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("printmaster")
    logger.setLevel(logging.INFO)
    for h in list(logger.handlers):
        logger.removeHandler(h)
        h.close()
    handler = RotatingFileHandler(log_dir / "printmaster.log", maxBytes=1_000_000,
                                  backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler.addFilter(RedactingFilter())
    logger.addHandler(handler)
    return logger
