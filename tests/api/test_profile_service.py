import asyncio
import time
import uuid
from datetime import datetime, timezone

import grpc
import jwt
import pytest
import pytest_asyncio
from grpc_reflection.v1alpha import reflection, reflection_pb2, reflection_pb2_grpc

from app import database, main
from shared.events import RegisteredUser, UserRegisteredEvent
from shared.proto import profile_pb2 as pb, profile_pb2_grpc as rpc


def event(user_id, event_id=None):
    now = datetime.now(timezone.utc)
    return UserRegisteredEvent(event_id=event_id or str(uuid.uuid4()), occurred_at=now,
        trace_id="profile-test", data=RegisteredUser(user_id=user_id, email="profile@example.com", created_at=now))


@pytest.fixture
def profile_db(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "profile.db"))
    database.init_database()


def test_atomic_creation_and_duplicate_preserves_changes(profile_db):
    user_id = str(uuid.uuid4())
    message = event(user_id)
    assert database.create_from_event(message)
    database.update_profile(user_id, {"first_name": "Vadim"})
    assert not database.create_from_event(message)
    assert database.create_from_event(event(user_id))
    assert database.get_profile(user_id)["first_name"] == "Vadim"
    with database.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM profiles").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM processed_events").fetchone()[0] == 2


def test_transaction_rolls_back_profile_when_event_insert_fails(profile_db):
    user_id = str(uuid.uuid4())
    with database.connect() as db:
        db.execute("CREATE TRIGGER reject_event BEFORE INSERT ON processed_events BEGIN SELECT RAISE(ABORT, 'test'); END")
    with pytest.raises(Exception, match="test"):
        database.create_from_event(event(user_id))
    assert database.get_profile(user_id) is None


@pytest.mark.parametrize("changes", [
    {}, {"birth_date": "tomorrow"}, {"birth_date": "2024-02-30"},
    {"birth_date": "2999-01-01"}, {"birth_date": "20000101"},
    {"first_name": "x" * 101}, {"description": "x" * 2001}, {"city": "a\x00b"},
])
def test_invalid_changes(changes):
    with pytest.raises(ValueError):
        main.validate_changes(pb.UpdateProfileRequest(user_id=str(uuid.uuid4()), **changes))


@pytest_asyncio.fixture
async def grpc_service(profile_db):
    server = grpc.aio.server()
    service = main.ProfileService()
    rpc.add_ProfileServiceServicer_to_server(service, server)
    reflection.enable_server_reflection((pb.DESCRIPTOR.services_by_name['ProfileService'].full_name, reflection.SERVICE_NAME), server)
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
        yield rpc.ProfileServiceStub(channel), service, channel
    await server.stop(0)


def metadata(user_id, **kwargs):
    token = jwt.encode({"sub": user_id, "exp": int(time.time()) + 60, **kwargs}, main.JWT_SECRET, algorithm="HS256")
    return (("authorization", "Bearer " + token), ("x-trace-id", "profile-rpc-test"))


@pytest.mark.asyncio
async def test_grpc_read_patch_clear_and_presence(grpc_service):
    stub, _, _ = grpc_service
    user_id = str(uuid.uuid4())
    database.create_from_event(event(user_id))
    await stub.UpdateProfile(pb.UpdateProfileRequest(user_id=user_id, first_name="Vadim", city="Moscow", birth_date="1990-01-02"), metadata=metadata(user_id))
    result = await stub.UpdateProfile(pb.UpdateProfileRequest(user_id=user_id, first_name=""), metadata=metadata(user_id))
    assert result.first_name == ""
    assert result.city == "Moscow"
    assert result.birth_date == "1990-01-02"
    assert (await stub.GetProfile(pb.GetProfileRequest(user_id=user_id), metadata=metadata(user_id))).city == "Moscow"


@pytest.mark.asyncio
async def test_grpc_missing_and_unauthorized(grpc_service):
    stub, _, _ = grpc_service
    user_id = str(uuid.uuid4())
    for headers, expected in [
        ((), grpc.StatusCode.UNAUTHENTICATED),
        (metadata(str(uuid.uuid4())), grpc.StatusCode.PERMISSION_DENIED),
        (metadata(user_id, exp=1), grpc.StatusCode.UNAUTHENTICATED),
        (metadata(user_id), grpc.StatusCode.NOT_FOUND),
    ]:
        with pytest.raises(grpc.aio.AioRpcError) as caught:
            await stub.GetProfile(pb.GetProfileRequest(user_id=user_id), metadata=headers)
        assert caught.value.code() == expected


@pytest.mark.asyncio
async def test_grpc_validation_deadline_and_no_delayed_write(grpc_service):
    stub, service, _ = grpc_service
    user_id = str(uuid.uuid4())
    database.create_from_event(event(user_id))
    with pytest.raises(grpc.aio.AioRpcError) as caught:
        await stub.UpdateProfile(pb.UpdateProfileRequest(user_id=user_id, birth_date="bad"), metadata=metadata(user_id))
    assert caught.value.code() == grpc.StatusCode.INVALID_ARGUMENT
    service.delay_ms = 200
    with pytest.raises(grpc.aio.AioRpcError) as caught:
        await stub.UpdateProfile(pb.UpdateProfileRequest(user_id=user_id, city="Late"), metadata=metadata(user_id), timeout=0.02)
    assert caught.value.code() == grpc.StatusCode.DEADLINE_EXCEEDED
    await asyncio.sleep(0.25)
    assert database.get_profile(user_id)["city"] == ""


@pytest.mark.asyncio
async def test_reflection_lists_profile_service(grpc_service):
    _, _, channel = grpc_service
    stub = reflection_pb2_grpc.ServerReflectionStub(channel)
    responses = stub.ServerReflectionInfo(iter([reflection_pb2.ServerReflectionRequest(list_services="")]))
    response = await responses.read()
    assert "qa.profile.v1.ProfileService" in [service.name for service in response.list_services_response.service]
