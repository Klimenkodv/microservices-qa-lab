from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import jwt
from aiokafka import AIOKafkaProducer
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from passlib.context import CryptContext
from prometheus_client import Counter, Gauge, generate_latest
from starlette.responses import Response

from shared.events import UserRegisteredEvent, kafka_headers
from shared.observability import configure_logging, install_http_middleware, trace_id_var

from . import database
from .config import settings
from .models import RegisterRequest, RegisterResponse, UserResponse

logger = configure_logging(settings.service_name)
passwords = CryptContext(schemes=["bcrypt"], deprecated="auto")
REGISTRATIONS = Counter("registrations_total", "Registration results", ["result"])
PUBLISHED = Counter("kafka_messages_published_total", "Published Kafka messages")
PUBLISH_FAILURES = Counter("kafka_publish_failures_total", "Kafka publish failures")
OUTBOX_PENDING = Gauge("outbox_pending_events", "Pending outbox events")
publisher_wakeup = asyncio.Event()
publisher_ready = asyncio.Event()


async def outbox_publisher(stop: asyncio.Event) -> None:
    while not stop.is_set():
        producer = AIOKafkaProducer(bootstrap_servers=settings.kafka_bootstrap_servers)
        try:
            await producer.start()
            publisher_ready.set()
            while not stop.is_set():
                rows = database.pending_events()
                OUTBOX_PENDING.set(database.pending_count())
                for row in rows:
                    try:
                        event = UserRegisteredEvent.model_validate_json(row["payload_json"])
                        await producer.send_and_wait(
                            settings.kafka_topic,
                            key=event.data.user_id.encode(),
                            value=json.dumps(event.model_dump(mode="json")).encode(),
                            headers=kafka_headers(event),
                        )
                        database.mark_published(event.event_id)
                        PUBLISHED.inc()
                        logger.info("Outbox event published", extra={"trace_id": event.trace_id, "event_id": event.event_id, "user_id": event.data.user_id, "email": event.data.email})
                    except Exception as exc:
                        database.mark_failed(row["id"], f"{type(exc).__name__}: {exc}")
                        PUBLISH_FAILURES.inc()
                        publisher_ready.clear()
                        logger.error("Outbox publish failed", extra={"event_id": row["id"], "error_type": type(exc).__name__})
                        raise
                publisher_wakeup.clear()
                try:
                    await asyncio.wait_for(publisher_wakeup.wait(), timeout=2)
                except TimeoutError:
                    pass
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            publisher_ready.clear()
            logger.error("Kafka producer unavailable; retrying", extra={"error_type": type(exc).__name__})
            await asyncio.sleep(3)
        finally:
            try:
                await producer.stop()
            except Exception:
                pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_database()
    stop = asyncio.Event()
    task = asyncio.create_task(outbox_publisher(stop))
    app.state.stop = stop
    app.state.publisher_task = task
    yield
    stop.set()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


app = FastAPI(title="QA Lab Auth Service", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Trace-ID"],
    expose_headers=["X-Trace-ID"],
)
install_http_middleware(app, settings.service_name)


def error_payload(code: str, message: str, status: int) -> JSONResponse:
    return JSONResponse(status_code=status, content={"code": code, "message": message, "trace_id": trace_id_var.get()})


@app.exception_handler(RequestValidationError)
async def validation_handler(_request: Request, exc: RequestValidationError):
    REGISTRATIONS.labels("validation_error").inc()
    details = []
    for error in exc.errors():
        field = str(error["loc"][-1])
        message = error["msg"].removeprefix("Value error, ")
        details.append({"field": field, "message": message})
    return JSONResponse(status_code=400, content={"detail": details})


@app.exception_handler(Exception)
async def unexpected_handler(_request: Request, exc: Exception):
    REGISTRATIONS.labels("error").inc()
    logger.exception("Unhandled API error", extra={"error_type": type(exc).__name__})
    return error_payload("INTERNAL_ERROR", "Internal server error", 500)


@app.post("/api/v1/register", response_model=RegisterResponse, status_code=201)
async def register(payload: RegisterRequest):
    trace_id = trace_id_var.get()
    password_hash = await asyncio.to_thread(passwords.hash, payload.password)
    try:
        user, event = await asyncio.to_thread(database.create_user_with_event, str(payload.email), password_hash, trace_id)
    except sqlite3.IntegrityError:
        REGISTRATIONS.labels("conflict").inc()
        logger.info("Registration conflict", extra={"email": str(payload.email)})
        return error_payload("EMAIL_ALREADY_EXISTS", "An account with this email already exists", 409)
    token = jwt.encode(
        {"sub": user["user_id"], "exp": datetime.now(timezone.utc) + timedelta(seconds=settings.jwt_ttl_seconds)},
        settings.jwt_secret,
        algorithm="HS256",
    )
    REGISTRATIONS.labels("success").inc()
    publisher_wakeup.set()
    logger.info("User registration accepted", extra={"event_id": event["event_id"], "user_id": user["user_id"], "email": user["email"]})
    return RegisterResponse(**user, access_token=token)


@app.get("/api/v1/me", response_model=UserResponse)
async def me(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        return error_payload("UNAUTHORIZED", "A valid bearer token is required", 401)
    try:
        claims = jwt.decode(authorization[7:], settings.jwt_secret, algorithms=["HS256"])
        user = await asyncio.to_thread(database.get_user, claims["sub"])
        if not user:
            raise ValueError("User not found")
    except Exception:
        return error_payload("UNAUTHORIZED", "The access token is invalid or expired", 401)
    return UserResponse(user_id=user["id"], email=user["email"], created_at=user["created_at"])


@app.get("/health")
async def health():
    try:
        await asyncio.to_thread(database.pending_count)
        return {"status": "healthy", "database": "up"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"database unavailable: {type(exc).__name__}")


@app.get("/ready")
async def ready():
    if not publisher_ready.is_set():
        raise HTTPException(status_code=503, detail="Kafka publisher is not ready")
    return {"status": "ready"}


@app.get("/metrics")
async def metrics():
    OUTBOX_PENDING.set(await asyncio.to_thread(database.pending_count))
    return Response(generate_latest(), media_type="text/plain; version=0.0.4")


@app.post("/internal/demo/retry-outbox", tags=["unsafe demo controls"])
async def retry_outbox():
    if not settings.demo_mode:
        raise HTTPException(status_code=404)
    count = await asyncio.to_thread(database.reset_failed_events)
    publisher_wakeup.set()
    return {"retried": count}
