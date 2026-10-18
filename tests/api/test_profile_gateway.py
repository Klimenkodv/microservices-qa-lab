import time
from types import SimpleNamespace

import grpc
import jwt
import pytest
from fastapi.testclient import TestClient

from app import main
from shared.proto import profile_pb2 as pb


@pytest.fixture
def gateway(monkeypatch):
    monkeypatch.setattr(main.database, "get_user", lambda user_id: {"id": user_id, "email": "qa@example.com", "created_at": "2026-01-01"})
    token = jwt.encode({"sub": "user-1", "exp": int(time.time()) + 60}, main.settings.jwt_secret, algorithm="HS256")
    return TestClient(main.app), {"Authorization": "Bearer " + token}


@pytest.mark.parametrize("grpc_code,http_code,error_code", [
    (grpc.StatusCode.NOT_FOUND, 404, "PROFILE_NOT_READY"),
    (grpc.StatusCode.UNAVAILABLE, 503, "PROFILE_UNAVAILABLE"),
    (grpc.StatusCode.DEADLINE_EXCEEDED, 504, "PROFILE_TIMEOUT"),
    (grpc.StatusCode.INVALID_ARGUMENT, 400, "INVALID_PROFILE"),
    (grpc.StatusCode.INTERNAL, 502, "PROFILE_ERROR"),
])
def test_grpc_error_mapping(gateway, grpc_code, http_code, error_code):
    client, headers = gateway
    async def fail(*args, **kwargs):
        raise grpc.aio.AioRpcError(grpc_code, (), (), "test")
    main.app.state.profile_stub = SimpleNamespace(GetProfile=fail)
    response = client.get("/api/v1/profile", headers={**headers, "X-Trace-ID": "gateway-test"})
    assert response.status_code == http_code
    assert response.json()["code"] == error_code
    assert response.json()["trace_id"] == "gateway-test"


def test_partial_patch_and_identity(gateway):
    client, headers = gateway
    async def update(request, **kwargs):
        assert request.user_id == "user-1"
        assert request.HasField("city") and not request.HasField("first_name")
        assert kwargs['timeout'] > 0
        assert ('x-trace-id', 'gateway-test') in kwargs['metadata']
        return pb.Profile(user_id=request.user_id, city=request.city)
    main.app.state.profile_stub = SimpleNamespace(UpdateProfile=update)
    response = client.patch("/api/v1/profile", headers={**headers, "X-Trace-ID": "gateway-test"}, json={"city": "Moscow"})
    assert response.status_code == 200
    assert response.json()["city"] == "Moscow"
    assert response.json()["first_name"] == ""
    assert client.patch("/api/v1/profile", headers=headers, json={"user_id": "other"}).status_code == 400
    assert client.get("/api/v1/profile").status_code == 401
