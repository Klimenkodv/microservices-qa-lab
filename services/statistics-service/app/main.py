from __future__ import annotations

import asyncio
import os
import sqlite3
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from prometheus_client import Counter, generate_latest
from starlette.responses import Response

from shared.consumer import consume_forever
from shared.events import UserRegisteredEvent
from shared.observability import configure_logging, install_http_middleware

SERVICE = "statistics-service"
DB_PATH = os.getenv("DATABASE_PATH", "/data/statistics.db")
KAFKA = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
TOPIC = os.getenv("KAFKA_TOPIC", "user.registered.v1")
DLQ_TOPIC = os.getenv("DLQ_TOPIC", "user.registered.dlq.v1")
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"
logger = configure_logging(SERVICE)
SAVED = Counter("statistics_events_saved_total", "Statistics events saved")
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
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS registration_events (
                event_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, email TEXT NOT NULL,
                registered_at TEXT NOT NULL, received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                trace_id TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS processed_events (
                event_id TEXT PRIMARY KEY, consumer_name TEXT NOT NULL,
                processed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )


def save_event(event: UserRegisteredEvent) -> bool:
    global failures_remaining
    with fault_lock:
        if failures_remaining > 0:
            failures_remaining -= 1
            raise RuntimeError("Injected statistics write failure")
    with db_lock, connect() as db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT 1 FROM processed_events WHERE event_id=?", (event.event_id,)).fetchone():
            return False
        db.execute(
            "INSERT INTO registration_events(event_id, user_id, email, registered_at, trace_id) VALUES (?, ?, ?, ?, ?)",
            (event.event_id, event.data.user_id, str(event.data.email), event.data.created_at.isoformat(), event.trace_id),
        )
        db.execute(
            "INSERT INTO processed_events(event_id, consumer_name) VALUES (?, ?)",
            (event.event_id, SERVICE),
        )
    return True


async def handle(event: UserRegisteredEvent):
    inserted = await asyncio.to_thread(save_event, event)
    if inserted:
        SAVED.inc()
        message = "Statistics event saved"
    else:
        message = "Duplicate statistics event skipped"
    logger.info(message, extra={"trace_id": event.trace_id, "event_id": event.event_id, "user_id": event.data.user_id, "email": str(event.data.email)})


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
        consume_forever(service=SERVICE, bootstrap_servers=KAFKA, group_id="statistics-service-group", topic=TOPIC, dlq_topic=DLQ_TOPIC, pause_event=pause, ready_event=ready, stop_event=stop, handler=handle, logger=logger)
    )
    yield
    stop.set()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


app = FastAPI(title="QA Lab Statistics Service", version="1.0.0", lifespan=lifespan)
install_http_middleware(app, SERVICE)


@app.get("/health")
async def health():
    try:
        await asyncio.to_thread(lambda: connect().close())
        return {"status": "healthy", "database": "up"}
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


@app.post("/internal/demo/fail-next-statistics-write", tags=["unsafe demo controls"])
async def fail_next_write():
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
