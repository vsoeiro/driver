"""Structured logging helpers."""

from __future__ import annotations

import json
import logging
from datetime import datetime, UTC
from typing import Any


def log_event(logger: logging.Logger, event: str, *, level: int = logging.INFO, **fields: Any) -> None:
    payload = {
        "event": event,
        "timestamp": datetime.now(UTC).isoformat(),
        **fields,
    }
    logger.log(level, json.dumps(payload, ensure_ascii=True, default=str))
