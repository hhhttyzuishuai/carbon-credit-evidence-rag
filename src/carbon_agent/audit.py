"""Append-only, privacy-aware execution audit log."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from .contracts import utc_now


SENSITIVE_KEY_PARTS = ("api_key", "token", "secret", "password")


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "***REDACTED***"
            if any(part in key.lower() for part in SENSITIVE_KEY_PARTS)
            else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


class JsonlAuditLog:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def write(self, event: dict[str, Any]) -> None:
        record = {"timestamp": utc_now(), **redact(event)}
        encoded = json.dumps(record, ensure_ascii=False, sort_keys=True)
        with self._lock, self.path.open("a", encoding="utf-8") as output:
            output.write(encoded + "\n")
            output.flush()

