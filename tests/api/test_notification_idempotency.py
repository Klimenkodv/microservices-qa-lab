from datetime import datetime, timezone

from shared.events import RegisteredUser, UserRegisteredEvent

from app import main


def test_notification_reservation_is_idempotent(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "DB_PATH", str(tmp_path / "notifications.db"))
    main.init_database()
    now = datetime.now(timezone.utc)
    event = UserRegisteredEvent(event_id="event-1", occurred_at=now, trace_id="trace", data=RegisteredUser(user_id="user", email="student@example.com", created_at=now))
    assert main.reserve_event(event) is True
    main.mark_sent(event.event_id)
    assert main.reserve_event(event) is False
