import os
import sqlite3
import time
from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.skipif(os.getenv("RUN_INTEGRATION") != "1", reason="requires running Docker Compose stack")
DATA_DIR = Path(__file__).parents[2] / "data"


def wait_for_row(database: str, query: str, value: str, timeout: float = 20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with sqlite3.connect(DATA_DIR / database) as connection:
                row = connection.execute(query, (value,)).fetchone()
                if row:
                    return row
        except sqlite3.OperationalError:
            pass
        time.sleep(0.25)
    pytest.fail(f"Expected row did not appear in {database}")


def test_registration_and_profile_round_trip():
    email = f"integration-{time.time_ns()}@example.com"
    response = httpx.post("http://localhost:8000/api/v1/register", json={"email": email, "password": "Password123"})
    assert response.status_code == 201
    token = response.json()["access_token"]
    profile = httpx.get("http://localhost:8000/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert profile.status_code == 200
    assert profile.json()["email"] == email
    assert wait_for_row("statistics.db", "SELECT event_id FROM registration_events WHERE email=?", email)
    assert wait_for_row("notifications.db", "SELECT event_id FROM sent_notifications WHERE email=? AND status='SENT'", email)


def test_invalid_payload_returns_400():
    response = httpx.post("http://localhost:8000/api/v1/register", json={"email": "bad", "password": "short"})
    assert response.status_code == 400
    assert isinstance(response.json()["detail"], list)


def test_duplicate_email_returns_409():
    email = f"duplicate-{time.time_ns()}@example.com"
    payload = {"email": email, "password": "Password123"}
    assert httpx.post("http://localhost:8000/api/v1/register", json=payload).status_code == 201
    second = httpx.post("http://localhost:8000/api/v1/register", json=payload)
    assert second.status_code == 409
    assert second.json()["code"] == "EMAIL_ALREADY_EXISTS"
