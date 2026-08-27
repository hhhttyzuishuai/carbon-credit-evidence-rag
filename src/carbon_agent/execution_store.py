"""SQLite execution ledger for idempotency, checkpoints, and replay."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from .contracts import utc_now


class IdempotencyConflict(ValueError):
    pass


@dataclass(frozen=True)
class ExecutionRecord:
    request_id: str
    fingerprint: str
    status: str
    step: int
    checkpoint: dict[str, Any]
    response: dict[str, Any] | None
    is_new: bool


class SQLiteExecutionStore:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS executions (
                    request_id TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL,
                    status TEXT NOT NULL,
                    step INTEGER NOT NULL DEFAULT 0,
                    checkpoint_json TEXT NOT NULL DEFAULT '{}',
                    response_json TEXT,
                    error_type TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS execution_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(request_id) REFERENCES executions(request_id)
                );

                CREATE INDEX IF NOT EXISTS idx_execution_events_request
                ON execution_events(request_id, event_id);
                """
            )

    def begin(self, request_id: str, fingerprint: str) -> ExecutionRecord:
        now = utc_now()
        with self._connection() as connection:
            # Serialize the read-then-create section so concurrent retries cannot
            # both pass the existence check for one idempotency key.
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM executions WHERE request_id = ?", (request_id,)
            ).fetchone()
            if row is None:
                connection.execute(
                    """
                    INSERT INTO executions(
                        request_id, fingerprint, status, step,
                        checkpoint_json, created_at, updated_at
                    ) VALUES (?, ?, 'running', 0, '{}', ?, ?)
                    """,
                    (request_id, fingerprint, now, now),
                )
                connection.execute(
                    """
                    INSERT INTO execution_events(
                        request_id, event_type, payload_json, created_at
                    ) VALUES (?, 'execution_started', '{}', ?)
                    """,
                    (request_id, now),
                )
                return ExecutionRecord(
                    request_id, fingerprint, "running", 0, {}, None, True
                )

            if row["fingerprint"] != fingerprint:
                raise IdempotencyConflict(
                    "相同 request_id 对应了不同请求内容，已拒绝重复执行。"
                )

            checkpoint = json.loads(row["checkpoint_json"] or "{}")
            response = (
                json.loads(row["response_json"])
                if row["response_json"]
                else None
            )
            if row["status"] != "completed":
                connection.execute(
                    """
                    UPDATE executions
                    SET status = 'running', error_type = NULL, updated_at = ?
                    WHERE request_id = ?
                    """,
                    (now, request_id),
                )
                connection.execute(
                    """
                    INSERT INTO execution_events(
                        request_id, event_type, payload_json, created_at
                    ) VALUES (?, 'execution_resumed', ?, ?)
                    """,
                    (
                        request_id,
                        json.dumps({"from_step": row["step"]}),
                        now,
                    ),
                )
            return ExecutionRecord(
                request_id=request_id,
                fingerprint=fingerprint,
                status=row["status"],
                step=int(row["step"]),
                checkpoint=checkpoint,
                response=response,
                is_new=False,
            )

    def save_checkpoint(
        self,
        request_id: str,
        step: int,
        checkpoint: dict[str, Any],
    ) -> None:
        now = utc_now()
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE executions
                SET step = ?, checkpoint_json = ?, status = 'running', updated_at = ?
                WHERE request_id = ?
                """,
                (
                    step,
                    json.dumps(checkpoint, ensure_ascii=False),
                    now,
                    request_id,
                ),
            )
            connection.execute(
                """
                INSERT INTO execution_events(
                    request_id, event_type, payload_json, created_at
                ) VALUES (?, 'checkpoint_saved', ?, ?)
                """,
                (request_id, json.dumps({"step": step}), now),
            )

    def append_event(
        self,
        request_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO execution_events(
                    request_id, event_type, payload_json, created_at
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    request_id,
                    event_type,
                    json.dumps(payload, ensure_ascii=False),
                    utc_now(),
                ),
            )

    def complete(self, request_id: str, response: dict[str, Any]) -> None:
        now = utc_now()
        encoded = json.dumps(response, ensure_ascii=False)
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE executions
                SET status = 'completed', response_json = ?, updated_at = ?
                WHERE request_id = ?
                """,
                (encoded, now, request_id),
            )
            connection.execute(
                """
                INSERT INTO execution_events(
                    request_id, event_type, payload_json, created_at
                ) VALUES (?, 'execution_completed', '{}', ?)
                """,
                (request_id, now),
            )

    def fail(self, request_id: str, error_type: str) -> None:
        now = utc_now()
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE executions
                SET status = 'failed', error_type = ?, updated_at = ?
                WHERE request_id = ?
                """,
                (error_type, now, request_id),
            )
            connection.execute(
                """
                INSERT INTO execution_events(
                    request_id, event_type, payload_json, created_at
                ) VALUES (?, 'execution_failed', ?, ?)
                """,
                (request_id, json.dumps({"error_type": error_type}), now),
            )

    def get_events(self, request_id: str) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT event_id, event_type, payload_json, created_at
                FROM execution_events
                WHERE request_id = ?
                ORDER BY event_id ASC
                """,
                (request_id,),
            ).fetchall()
        return [
            {
                "event_id": row["event_id"],
                "event_type": row["event_type"],
                "payload": json.loads(row["payload_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]
