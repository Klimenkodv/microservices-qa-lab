import importlib
import sqlite3

import pytest
from pydantic import ValidationError

from app.models import RegisterRequest


def test_normalizes_email():
    model = RegisterRequest(email="  Student@Example.COM ", password="Password123")
    assert str(model.email) == "student@example.com"


@pytest.mark.parametrize("password", ["short1", "onlyletters", "12345678"])
def test_rejects_weak_passwords(password):
    with pytest.raises(ValidationError):
        RegisterRequest(email="student@example.com", password=password)


def test_accepts_valid_password():
    assert RegisterRequest(email="student@example.com", password="Password123").password == "Password123"


def test_transaction_creates_user_and_outbox(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "auth.db"))
    from app import config, database
    importlib.reload(config)
    importlib.reload(database)
    database.init_database()
    user, event = database.create_user_with_event("student@example.com", "safe-hash", "trace-1")
    assert user["user_id"] == event["data"]["user_id"]
    assert database.pending_count() == 1


def test_duplicate_email_rolls_back_second_outbox(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "auth.db"))
    from app import config, database
    importlib.reload(config)
    importlib.reload(database)
    database.init_database()
    database.create_user_with_event("student@example.com", "hash", "trace-1")
    with pytest.raises(sqlite3.IntegrityError):
        database.create_user_with_event("STUDENT@example.com", "hash", "trace-2")
    assert database.pending_count() == 1


def test_outbox_status_transition(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "auth.db"))
    from app import config, database
    importlib.reload(config)
    importlib.reload(database)
    database.init_database()
    _, event = database.create_user_with_event("student@example.com", "hash", "trace")
    database.mark_published(event["event_id"])
    assert database.pending_count() == 0
