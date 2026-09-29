from datetime import datetime, timezone

from shared.events import RegisteredUser, UserRegisteredEvent

from app import main


def test_statistics_save_is_idempotent(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "DB_PATH", str(tmp_path / "statistics.db"))
    main.init_database()
    now = datetime.now(timezone.utc)
    event = UserRegisteredEvent(event_id="event-1", occurred_at=now, trace_id="trace", data=RegisteredUser(user_id="user", email="student@example.com", created_at=now))
    assert main.save_event(event) is True
    assert main.save_event(event) is False
    with main.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM registration_events").fetchone()[0] == 1
