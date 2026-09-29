from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr


class RegisteredUser(BaseModel):
    user_id: str
    email: EmailStr
    created_at: datetime


class UserRegisteredEvent(BaseModel):
    event_id: str
    event_type: Literal["user.registered"] = "user.registered"
    event_version: Literal[1] = 1
    occurred_at: datetime
    trace_id: str
    data: RegisteredUser


def kafka_headers(event: UserRegisteredEvent) -> list[tuple[str, bytes]]:
    return [
        ("trace_id", event.trace_id.encode()),
        ("event_id", event.event_id.encode()),
        ("event_type", event.event_type.encode()),
        ("schema_version", b"1"),
    ]
