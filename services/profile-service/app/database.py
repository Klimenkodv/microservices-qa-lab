from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from shared.events import UserRegisteredEvent

DB_PATH = os.getenv("DATABASE_PATH", "/data/profile.db")
FIELDS = ("first_name", "last_name", "birth_date", "city", "description", "country")


@contextmanager
def connect():
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA journal_mode=WAL")
        with db:
            yield db
    finally:
        db.close()


def init_database():
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    with connect() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS profiles (
                user_id TEXT PRIMARY KEY,
                first_name TEXT NOT NULL DEFAULT '', last_name TEXT NOT NULL DEFAULT '',
                birth_date TEXT NOT NULL DEFAULT '', city TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '', country TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS processed_events (
                event_id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                consumer_name TEXT NOT NULL,
                processed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
        """)


def create_from_event(event: UserRegisteredEvent) -> bool:
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT 1 FROM processed_events WHERE event_id=?", (event.event_id,)).fetchone():
            return False
        timestamp = event.data.created_at.isoformat()
        db.execute("INSERT OR IGNORE INTO profiles(user_id, created_at, updated_at) VALUES (?, ?, ?)",
                   (event.data.user_id, timestamp, timestamp))
        db.execute("INSERT INTO processed_events(event_id, user_id, consumer_name) VALUES (?, ?, ?)",
                   (event.event_id, event.data.user_id, "profile-service"))
    return True


def get_profile(user_id: str):
    with connect() as db:
        row = db.execute("SELECT * FROM profiles WHERE user_id=?", (user_id,)).fetchone()
        return dict(row) if row else None


def update_profile(user_id: str, changes: dict[str, str]):
    if not changes or not set(changes).issubset(FIELDS):
        raise ValueError("Only editable profile fields are accepted")
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        # Column names come exclusively from the fixed allowlist above.
        assignments = ", ".join(f"{field}=?" for field in changes)
        now = datetime.now(timezone.utc).isoformat()
        db.execute(f"UPDATE profiles SET {assignments}, updated_at=? WHERE user_id=?",
                   (*changes.values(), now, user_id))
        row = db.execute("SELECT * FROM profiles WHERE user_id=?", (user_id,)).fetchone()
        return dict(row) if row else None
