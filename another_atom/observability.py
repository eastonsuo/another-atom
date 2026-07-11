"""Process logs for operators; RunEvent remains the user-facing audit trail."""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from another_atom.config import get_settings


class JsonFormatter(logging.Formatter):
    """Emit small, machine-readable records without request or model contents."""

    _context_fields = ("run_id", "project_id", "job_id", "stage", "provider", "status")

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in self._context_fields:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging() -> None:
    """Configure the application logger once, leaving Uvicorn's logger untouched."""
    logger = logging.getLogger("another_atom")
    if any(getattr(handler, "_another_atom_handler", False) for handler in logger.handlers):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler._another_atom_handler = True  # type: ignore[attr-defined]
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(get_settings().log_level.upper())
    logger.propagate = False


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"another_atom.{name}")
