from __future__ import annotations

import json
import logging
import sys
from typing import Any, Mapping


class JSONLogFormatter(logging.Formatter):
    """Simple log formatter that emits JSON lines."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.__dict__.get("error"):
            payload["error"] = record.__dict__["error"]
        return json.dumps(payload, ensure_ascii=False)


def configure_root_logger(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONLogFormatter())
    logging.basicConfig(level=level, handlers=[handler])
