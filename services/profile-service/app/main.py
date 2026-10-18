from __future__ import annotations

import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from datetime import date

import grpc
import jwt
from fastapi import FastAPI, HTTPException
from grpc_health.v1 import health, health_pb2, health_pb2_grpc
from grpc_reflection.v1alpha import reflection
from prometheus_client import Counter, Histogram, generate_latest
from pydantic import BaseModel, Field
from starlette.responses import Response

from shared.consumer import consume_forever
from shared.observability import configure_logging, install_http_middleware, trace_id_var
from shared.proto import profile_pb2 as pb, profile_pb2_grpc as rpc
from . import database

SERVICE = "profile-service"
JWT_SECRET = os.getenv("JWT_SECRET", "local-demo-secret-change-me")
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"
GRPC_ADDRESS = os.getenv("GRPC_LISTEN_ADDRESS", "[::]:50051")
logger = configure_logging(SERVICE)
REQUESTS = Counter("grpc_server_requests_total", "Profile RPC results", ["method", "status"])
DURATION = Histogram("grpc_server_duration_seconds", "Profile RPC duration", ["method"])
CREATED = Counter("profiles_created_events_total", "Processed profile creation events")


def validate_user_id(value: str):
    try:
        uuid.UUID(value)
    except (ValueError, AttributeError):
        raise ValueError("user_id must be a UUID")


def validate_changes(request):
    changes = {field: getattr(request, field) for field in database.FIELDS if request.HasField(field)}
    if not changes:
        raise ValueError("Provide at least one editable field")
    limits = {"first_name": 100, "last_name": 100, "city": 100, "country": 100, "description": 2000}
    for field, value in changes.items():
        if field in limits and len(value) > limits[field]:
            raise ValueError(f"{field} exceeds {limits[field]} characters")
        if "\x00" in value:
            raise ValueError(f"{field} contains an invalid character")
    birth = changes.get("birth_date")
    if birth:
        try:
            parsed = date.fromisoformat(birth)
        except ValueError:
            raise ValueError("birth_date must be YYYY-MM-DD")
        if parsed.isoformat() != birth or parsed > date.today():
            raise ValueError("birth_date must be YYYY-MM-DD and not in the future")
    return changes


class ProfileService(rpc.ProfileServiceServicer):
    def __init__(self):
        self.delay_ms = 0

    async def execute(self, method, request, context):
        metadata = dict(context.invocation_metadata())
        trace = metadata.get("x-trace-id") or str(uuid.uuid4())
        token = trace_id_var.set(trace)
        status = "INTERNAL"
        started = asyncio.get_running_loop().time()
        try:
            validate_user_id(request.user_id)
            authorization = metadata.get("authorization", "")
            if not authorization.startswith("Bearer "):
                status = "UNAUTHENTICATED"
                await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Bearer token is required")
            try:
                claims = jwt.decode(authorization[7:], JWT_SECRET, algorithms=["HS256"])
                subject = claims["sub"]
            except (jwt.PyJWTError, KeyError):
                status = "UNAUTHENTICATED"
                await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid or expired token")
            if subject != request.user_id:
                status = "PERMISSION_DENIED"
                await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Only your own profile is accessible")
            changes = validate_changes(request) if method == "UpdateProfile" else None
            if self.delay_ms:
                await asyncio.sleep(self.delay_ms / 1000)
            if changes is None:
                profile = await asyncio.to_thread(database.get_profile, request.user_id)
            else:
                profile = await asyncio.to_thread(database.update_profile, request.user_id, changes)
            if profile is None:
                status = "NOT_FOUND"
                await context.abort(grpc.StatusCode.NOT_FOUND, "Profile has not been created yet")
            status = "OK"
            return pb.Profile(**profile)
        except ValueError as exc:
            status = "INVALID_ARGUMENT"
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))
        except asyncio.CancelledError:
            status = "CANCELLED"
            raise
        except grpc.aio.AbortError:
            raise
        except Exception:
            status = "INTERNAL"
            logger.exception("Profile storage operation failed", extra={"user_id": request.user_id})
            await context.abort(grpc.StatusCode.INTERNAL, "Profile storage unavailable")
        finally:
            REQUESTS.labels(method, status).inc()
            DURATION.labels(method).observe(asyncio.get_running_loop().time() - started)
            log = logger.info if status == "OK" else logger.warning
            log(f"gRPC {method} {status}", extra={"user_id": request.user_id, "error_type": status if status != "OK" else None})
            trace_id_var.reset(token)

    async def GetProfile(self, request, context):
        return await self.execute("GetProfile", request, context)

    async def UpdateProfile(self, request, context):
        return await self.execute("UpdateProfile", request, context)


async def handle(event):
    inserted = await asyncio.to_thread(database.create_from_event, event)
    if inserted:
        CREATED.inc()
    logger.info("Profile event processed" if inserted else "Duplicate profile event skipped",
                extra={"trace_id": event.trace_id, "event_id": event.event_id, "user_id": event.data.user_id})


@asynccontextmanager
async def lifespan(app):
    await asyncio.to_thread(database.init_database)
    server = grpc.aio.server()
    servicer = ProfileService()
    rpc.add_ProfileServiceServicer_to_server(servicer, server)
    health_service = health.aio.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_service, server)
    service_name = pb.DESCRIPTOR.services_by_name["ProfileService"].full_name
    if DEMO_MODE:
        reflection.enable_server_reflection((service_name, health.SERVICE_NAME, reflection.SERVICE_NAME), server)
    if not server.add_insecure_port(GRPC_ADDRESS):
        raise RuntimeError("Could not bind gRPC port")
    await server.start()
    await health_service.set(service_name, health_pb2.HealthCheckResponse.SERVING)
    await health_service.set("", health_pb2.HealthCheckResponse.SERVING)
    app.state.grpc = servicer
    app.state.pause = asyncio.Event()
    app.state.pause.set()
    app.state.ready = asyncio.Event()
    stop = asyncio.Event()
    task = asyncio.create_task(consume_forever(
        service=SERVICE, bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092"),
        group_id="profile-service-group", topic=os.getenv("KAFKA_TOPIC", "user.registered.v1"),
        dlq_topic=os.getenv("DLQ_TOPIC", "user.registered.dlq.v1"),
        pause_event=app.state.pause, ready_event=app.state.ready, stop_event=stop,
        handler=handle, logger=logger))
    try:
        yield
    finally:
        stop.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await health_service.enter_graceful_shutdown()
        await server.stop(2)


app = FastAPI(title="QA Lab Profile Service: operations", version="1.0.0", lifespan=lifespan)
install_http_middleware(app, SERVICE)


@app.get("/health")
async def health_check():
    try:
        with database.connect() as db:
            db.execute("SELECT 1 FROM profiles LIMIT 1")
        return {"status": "healthy", "database": "up", "grpc_port": 50051}
    except Exception:
        raise HTTPException(status_code=503, detail="Profile database unavailable")


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


class DelayRequest(BaseModel):
    delay_ms: int = Field(ge=0, le=10000)


@app.post("/internal/demo/grpc-delay", tags=["unsafe demo controls"])
async def grpc_delay(payload: DelayRequest):
    require_demo()
    app.state.grpc.delay_ms = payload.delay_ms
    return {"delay_ms": payload.delay_ms}


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
