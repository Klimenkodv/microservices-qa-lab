import os
import time

import grpc
import httpx
import pytest

from shared.proto import profile_pb2 as pb, profile_pb2_grpc as rpc

pytestmark = pytest.mark.skipif(os.getenv("RUN_INTEGRATION") != "1", reason="requires Docker Compose stack")


def test_profile_round_trip_and_access_boundaries():
    response = httpx.post("http://localhost:8000/api/v1/register", json={
        "email": f"profile-{time.time_ns()}@example.com", "password": "Password123"})
    assert response.status_code == 201
    user = response.json()
    headers = {"Authorization": "Bearer " + user['access_token'], "X-Trace-ID": "profile-integration"}
    deadline = time.monotonic() + 30
    while True:
        response = httpx.get("http://localhost:8000/api/v1/profile", headers=headers)
        if response.status_code == 200:
            break
        assert response.status_code == 404
        assert time.monotonic() < deadline, response.text
        time.sleep(0.25)
    assert response.json()['first_name'] == ''
    updated = httpx.patch("http://localhost:8000/api/v1/profile", headers=headers,
        json={"first_name": "QA", "last_name": "Student", "birth_date": "1990-05-21", "city": "Moscow", "description": "Day 6"})
    assert updated.status_code == 200, updated.text
    with grpc.insecure_channel("localhost:50051") as channel:
        stub = rpc.ProfileServiceStub(channel)
        metadata = (("authorization", headers['Authorization']), ("x-trace-id", 'profile-integration'))
        profile = stub.GetProfile(pb.GetProfileRequest(user_id=user['user_id']), metadata=metadata, timeout=3)
        assert profile.first_name == 'QA' and profile.city == 'Moscow'
        with pytest.raises(grpc.RpcError) as caught:
            stub.UpdateProfile(pb.UpdateProfileRequest(user_id=user['user_id'], birth_date='bad'), metadata=metadata, timeout=3)
        assert caught.value.code() == grpc.StatusCode.INVALID_ARGUMENT
        with pytest.raises(grpc.RpcError) as caught:
            stub.GetProfile(pb.GetProfileRequest(user_id=user['user_id']), timeout=3)
        assert caught.value.code() == grpc.StatusCode.UNAUTHENTICATED
    cleared = httpx.patch("http://localhost:8000/api/v1/profile", headers=headers, json={"first_name": ""})
    assert cleared.json()['first_name'] == '' and cleared.json()['city'] == 'Moscow'
    assert httpx.get("http://localhost:8000/api/v1/profile").status_code == 401
