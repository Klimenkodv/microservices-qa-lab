from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from shared.events import RegisteredUser, UserRegisteredEvent, kafka_headers


def event():
    now = datetime.now(timezone.utc)
    return UserRegisteredEvent(event_id="event-1", occurred_at=now, trace_id="trace-1", data=RegisteredUser(user_id="user-1", email="student@example.com", created_at=now))


def test_event_contract_version_is_one():
    assert event().event_version == 1


def test_event_rejects_unknown_type():
    payload = event().model_dump()
    payload["event_type"] = "user.deleted"
    with pytest.raises(ValidationError):
        UserRegisteredEvent.model_validate(payload)


def test_kafka_headers_carry_correlation_fields():
    headers = dict(kafka_headers(event()))
    assert headers["trace_id"] == b"trace-1"
    assert headers["event_id"] == b"event-1"
    assert headers["schema_version"] == b"1"
