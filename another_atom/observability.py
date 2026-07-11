"""Process logs for operators; RunEvent remains the user-facing audit trail."""

import json
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
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


def _log_file_path(directory: Path, process_started_at: datetime) -> Path:
    filename = f"atom-{os.getpid()}-{process_started_at.strftime('%Y%m%d-%H%M%S')}.log"
    return directory / filename


def configure_logging() -> None:
    """Configure the application logger once, leaving Uvicorn's logger untouched."""
    logger = logging.getLogger("another_atom")
    if any(getattr(handler, "_another_atom_handler", False) for handler in logger.handlers):
        return
    settings = get_settings()
    formatter = JsonFormatter()
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler._another_atom_handler = True  # type: ignore[attr-defined]
    stdout_handler.setFormatter(formatter)
    logger.addHandler(stdout_handler)

    process_started_at = datetime.now(UTC)
    log_directory = settings.log_directory.resolve()
    log_directory.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(
        _log_file_path(log_directory, process_started_at), encoding="utf-8"
    )
    file_handler._another_atom_handler = True  # type: ignore[attr-defined]
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.setLevel(settings.log_level.upper())
    logger.propagate = False


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"another_atom.{name}")
