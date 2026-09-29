from __future__ import annotations

import asyncio
import os
import smtplib
import sqlite3
import threading
from contextlib import asynccontextmanager
from email.message import EmailMessage

from fastapi import FastAPI, HTTPException
from prometheus_client import Counter, generate_latest
from starlette.responses import Response

from shared.consumer import consume_forever
from shared.events import UserRegisteredEvent
from shared.observability import configure_logging, install_http_middleware

SERVICE = "notification-service"
DB_PATH = os.getenv("DATABASE_PATH", "/data/notifications.db")
KAFKA = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
TOPIC = os.getenv("KAFKA_TOPIC", "user.registered.v1")
DLQ_TOPIC = os.getenv("DLQ_TOPIC", "user.registered.dlq.v1")
SMTP_HOST = os.getenv("SMTP_HOST", "mailpit")
SMTP_PORT = int(os.getenv("SMTP_PORT", "1025"))
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"
logger = configure_logging(SERVICE)
SENT = Counter("notifications_sent_total", "Notifications sent")
FAILED = Counter("notifications_failed_total", "Notification failures")
db_lock = threading.Lock()
fault_lock = threading.Lock()
failures_remaining = 0


def connect():
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    return db


def init_database():
    with connect() as db:
        db.execute(
            """CREATE TABLE IF NOT EXISTS sent_notifications (
                event_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, email TEXT NOT NULL,
                sent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, status TEXT NOT NULL
            )"""
        )


def reserve_event(event: UserRegisteredEvent) -> bool:
    with db_lock, connect() as db:
        row = db.execute("SELECT status FROM sent_notifications WHERE event_id=?", (event.event_id,)).fetchone()
        if row and row["status"] == "SENT":
            return False
        db.execute(
            "INSERT OR REPLACE INTO sent_notifications(event_id, user_id, email, status) VALUES (?, ?, ?, 'PENDING')",
            (event.event_id, event.data.user_id, str(event.data.email)),
        )
    return True


def mark_sent(event_id: str):
    with db_lock, connect() as db:
        db.execute("UPDATE sent_notifications SET status='SENT', sent_at=CURRENT_TIMESTAMP WHERE event_id=?", (event_id,))


def send_email(event: UserRegisteredEvent):
    global failures_remaining
    with fault_lock:
        if failures_remaining > 0:
            failures_remaining -= 1
            raise RuntimeError("Injected email delivery failure")
    message = EmailMessage()
    message["From"] = "qa-lab@example.test"
    message["To"] = str(event.data.email)
    message["Subject"] = "Confirm your QA Lab account"
    message.set_content(
        f"Hello!\n\nConfirm the demo account:\n"
        "http://localhost:8000/api/v1/confirm-email?token=demo-token\n"
    )
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as smtp:
        smtp.send_message(message)


async def handle(event: UserRegisteredEvent):
    if not await asyncio.to_thread(reserve_event, event):
        logger.info("Duplicate notification skipped", extra={"trace_id": event.trace_id, "event_id": event.event_id, "user_id": event.data.user_id, "email": str(event.data.email)})
        return
    try:
        await asyncio.to_thread(send_email, event)
        await asyncio.to_thread(mark_sent, event.event_id)
        SENT.inc()
        logger.info("Notification sent", extra={"trace_id": event.trace_id, "event_id": event.event_id, "user_id": event.data.user_id, "email": str(event.data.email)})
    except Exception:
        FAILED.inc()
        raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    await asyncio.to_thread(init_database)
    pause = asyncio.Event()
    pause.set()
    ready = asyncio.Event()
    stop = asyncio.Event()
    app.state.pause = pause
    app.state.ready = ready
    app.state.stop = stop
    task = asyncio.create_task(
        consume_forever(service=SERVICE, bootstrap_servers=KAFKA, group_id="notification-service-group", topic=TOPIC, dlq_topic=DLQ_TOPIC, pause_event=pause, ready_event=ready, stop_event=stop, handler=handle, logger=logger)
    )
    yield
    stop.set()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


app = FastAPI(title="QA Lab Notification Service", version="1.0.0", lifespan=lifespan)
install_http_middleware(app, SERVICE)


@app.get("/health")
async def health():
    try:
        await asyncio.to_thread(lambda: connect().close())
        await asyncio.to_thread(lambda: smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=3).quit())
        return {"status": "healthy", "database": "up", "smtp": "up"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=type(exc).__name__)


@app.get("/ready")
async def ready():
    if not app.state.ready.is_set():
        raise HTTPException(status_code=503, detail="Kafka consumer is not ready")
    return {"status": "ready", "paused": not app.state.pause.is_set()}


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type="text/plain; version=0.0.4")


def require_demo():
    if not DEMO_MODE:
        raise HTTPException(status_code=404)


@app.post("/internal/demo/fail-next-email", tags=["unsafe demo controls"])
async def fail_next_email():
    global failures_remaining
    require_demo()
    with fault_lock:
        failures_remaining = 3
    return {"status": "armed", "failed_attempts": 3}


@app.post("/internal/demo/pause-consumer", tags=["unsafe demo controls"])
async def pause_consumer():
    require_demo()
    app.state.pause.clear()
    return {"status": "paused"}


@app.post("/internal/demo/resume-consumer", tags=["unsafe demo controls"])
async def resume_consumer():
    require_demo()
    app.state.pause.set()
    return {"status": "running"}
