from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .heuristics import extract_first_code

APPLE_EPOCH_UNIX_SECONDS = 978307200


@dataclass(slots=True)
class IMessageRecord:
    sender: str
    text: str
    received_at: datetime


def _apple_timestamp_to_datetime(raw: int | float | None) -> datetime:
    if not raw:
        return datetime.now(timezone.utc)
    numeric = float(raw)
    if numeric > 10_000_000_000:
        numeric = numeric / 1_000_000_000
    unix_seconds = numeric + APPLE_EPOCH_UNIX_SECONDS
    return datetime.fromtimestamp(unix_seconds, tz=timezone.utc)


class IMessageCodeWatcher:
    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = Path(db_path or "~/Library/Messages/chat.db").expanduser()

    def _connect(self) -> sqlite3.Connection:
        if not self._db_path.exists():
            raise FileNotFoundError(f"iMessage database not found: {self._db_path}")
        connection = sqlite3.connect(str(self._db_path))
        connection.row_factory = sqlite3.Row
        return connection

    def list_recent_messages(self, limit: int = 30) -> list[IMessageRecord]:
        query = """
        SELECT
            COALESCE(handle.id, '') AS sender,
            COALESCE(message.text, '') AS text,
            message.date AS raw_date
        FROM message
        LEFT JOIN handle ON message.handle_id = handle.ROWID
        WHERE message.is_from_me = 0
          AND message.text IS NOT NULL
          AND message.text != ''
        ORDER BY message.date DESC
        LIMIT ?
        """
        with self._connect() as connection:
            rows = connection.execute(query, (limit,)).fetchall()

        records: list[IMessageRecord] = []
        for row in rows:
            records.append(
                IMessageRecord(
                    sender=row["sender"],
                    text=row["text"],
                    received_at=_apple_timestamp_to_datetime(row["raw_date"]),
                ),
            )
        return records

    def wait_for_code(
        self,
        timeout_seconds: int = 180,
        sender_keywords: list[str] | None = None,
        body_keywords: list[str] | None = None,
        since: datetime | None = None,
        poll_interval_seconds: float = 2.0,
    ) -> str:
        deadline = time.time() + timeout_seconds
        sender_keywords = [item.lower() for item in (sender_keywords or []) if item]
        body_keywords = body_keywords or []

        while time.time() < deadline:
            for record in self.list_recent_messages():
                if since and record.received_at <= since:
                    continue
                sender_lower = record.sender.lower()
                if sender_keywords and not any(key in sender_lower for key in sender_keywords):
                    continue
                code = extract_first_code(record.text, preferred_keywords=body_keywords)
                if code:
                    return code
            time.sleep(poll_interval_seconds)

        raise TimeoutError(f"No verification code found in iMessage within {timeout_seconds} seconds.")

