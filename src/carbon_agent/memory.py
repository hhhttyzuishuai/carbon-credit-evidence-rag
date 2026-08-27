"""SQLite-backed durable conversation memory."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from .contracts import Message, utc_now


class SQLiteConversationStore:
    """Persist sessions and complete user/assistant turns in one local database."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        """Commit or roll back a transaction, then always release the file handle."""
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
                );

                CREATE INDEX IF NOT EXISTS idx_messages_session_order
                ON messages(session_id, message_id);
                """
            )

    def create_session(self, session_id: str | None = None) -> str:
        resolved_id = session_id or uuid4().hex
        timestamp = utc_now()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO sessions(session_id, created_at, updated_at)
                VALUES (?, ?, ?)
                """,
                (resolved_id, timestamp, timestamp),
            )
        return resolved_id

    def session_exists(self, session_id: str) -> bool:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT 1 FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        return row is not None

    def record_turn(self, session_id: str, user_text: str, answer: str) -> None:
        """Atomically persist both sides of a completed turn."""
        timestamp = utc_now()
        with self._connection() as connection:
            if not connection.execute(
                "SELECT 1 FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone():
                raise KeyError(f"会话不存在：{session_id}")

            connection.executemany(
                """
                INSERT INTO messages(session_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (session_id, "user", user_text, timestamp),
                    (session_id, "assistant", answer, timestamp),
                ],
            )
            connection.execute(
                "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
                (timestamp, session_id),
            )

    def get_history(self, session_id: str, limit: int = 12) -> list[Message]:
        if limit <= 0:
            return []
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT role, content, created_at
                FROM (
                    SELECT message_id, role, content, created_at
                    FROM messages
                    WHERE session_id = ?
                    ORDER BY message_id DESC
                    LIMIT ?
                )
                ORDER BY message_id ASC
                """,
                (session_id, limit),
            ).fetchall()
        return [
            Message(
                role=row["role"],
                content=row["content"],
                created_at=row["created_at"],
            )
            for row in rows
        ]
