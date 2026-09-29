from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone

from .config import settings

_lock = threading.Lock()


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(settings.database_path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def init_database() -> None:
    with connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS outbox_events (
                id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                aggregate_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'NEW',
                attempts INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                published_at TEXT,
                last_error TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_outbox_status_created ON outbox_events(status, created_at);
            """
        )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def create_user_with_event(email: str, password_hash: str, trace_id: str) -> tuple[dict, dict]:
    user_id = str(uuid.uuid4())
    event_id = str(uuid.uuid4())
    now = utc_now()
    event = {
        "event_id": event_id,
        "event_type": "user.registered",
        "event_version": 1,
        "occurred_at": now,
        "trace_id": trace_id,
        "data": {"user_id": user_id, "email": email, "created_at": now},
    }
    with _lock, connect() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            "INSERT INTO users(id, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (user_id, email, password_hash, now),
        )
        db.execute(
            "INSERT INTO outbox_events(id, event_type, aggregate_id, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (event_id, "user.registered", user_id, json.dumps(event), now),
        )
    return event["data"], event


def get_user(user_id: str):
    with connect() as db:
        row = db.execute("SELECT id, email, created_at FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def pending_events() -> list[sqlite3.Row]:
    with connect() as db:
        return list(db.execute("SELECT * FROM outbox_events WHERE status IN ('NEW', 'FAILED') ORDER BY created_at LIMIT 100"))


def mark_published(event_id: str) -> None:
    with connect() as db:
        db.execute(
            "UPDATE outbox_events SET status='PUBLISHED', published_at=?, last_error=NULL WHERE id=?",
            (utc_now(), event_id),
        )


def mark_failed(event_id: str, error: str) -> None:
    with connect() as db:
        db.execute(
            "UPDATE outbox_events SET status='FAILED', attempts=attempts+1, last_error=? WHERE id=?",
            (error[:500], event_id),
        )


def pending_count() -> int:
    with connect() as db:
        return db.execute("SELECT COUNT(*) FROM outbox_events WHERE status IN ('NEW', 'FAILED')").fetchone()[0]


def reset_failed_events() -> int:
    with connect() as db:
        cursor = db.execute("UPDATE outbox_events SET status='NEW', last_error=NULL WHERE status='FAILED'")
        return cursor.rowcount
