from __future__ import annotations

import json
import logging
import os
import sys
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone

from fastapi import Request, Response
from prometheus_client import Counter, Histogram

trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")

HTTP_REQUESTS = Counter(
    "http_requests_total", "HTTP requests", ["service", "method", "path", "status"]
)
HTTP_DURATION = Histogram(
    "http_request_duration_seconds", "HTTP request duration", ["service", "method", "path"]
)


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str) -> None:
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "service": self.service,
            "message": record.getMessage(),
            "trace_id": getattr(record, "trace_id", None) or trace_id_var.get() or None,
            "event_id": getattr(record, "event_id", None),
            "user_id": getattr(record, "user_id", None),
            "email": getattr(record, "email", None),
        }
        if hasattr(record, "error_type"):
            payload["error_type"] = record.error_type
        if record.exc_info and os.getenv("ENVIRONMENT", "development") == "development":
            payload["stack_trace"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(service: str) -> logging.Logger:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(os.getenv("LOG_LEVEL", "INFO"))
    return logging.getLogger(service)


def install_http_middleware(app, service: str) -> None:
    @app.middleware("http")
    async def observe_request(request: Request, call_next):
        trace_id = request.headers.get("X-Trace-ID") or str(uuid.uuid4())
        token = trace_id_var.set(trace_id)
        started = time.perf_counter()
        status = 500
        try:
            response: Response = await call_next(request)
            status = response.status_code
            response.headers["X-Trace-ID"] = trace_id
            return response
        finally:
            path = request.scope.get("route").path if request.scope.get("route") else request.url.path
            HTTP_REQUESTS.labels(service, request.method, path, str(status)).inc()
            HTTP_DURATION.labels(service, request.method, path).observe(time.perf_counter() - started)
            trace_id_var.reset(token)
