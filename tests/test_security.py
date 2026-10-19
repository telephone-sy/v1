from collections import defaultdict
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from redis.exceptions import RedisError

from models import AuthSession
from services.rate_limit import clear_memory_rate_limits, enforce_rate_limit
from settings import Settings
from security_middleware import RequestBodyLimitMiddleware
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient


def test_session_cookie_is_http_only_strict_and_revoked(client):
    response = client.post("/api/auth/register", json={
        "name":"عضو أمان",
        "phone":"0912345678",
        "password":"LongPass1234",
    })
    assert response.status_code == 201
    raw_token = client.cookies.get("telephone_sy_session")
    assert raw_token and len(raw_token) >= 40
    cookie_header = response.headers["set-cookie"].lower()
    assert "httponly" in cookie_header
    assert "samesite=strict" in cookie_header
    assert "secure" not in cookie_header

    with client.app.state.test_session_factory() as db:
        saved = db.scalar(select(AuthSession))
        assert saved is not None
        assert saved.token_hash != raw_token

    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").json() is None
    with client.app.state.test_session_factory() as db:
        assert db.scalar(select(AuthSession)) is None


def test_registration_rate_limit(client):
    clear_memory_rate_limits()
    for index in range(5):
        response = client.post("/api/auth/register", json={
            "name":f"عضو {index}",
            "phone":f"09{index:08d}",
            "password":"LongPass1234",
        })
        assert response.status_code == 201
    blocked = client.post("/api/auth/register", json={
        "name":"مستخدم إضافي",
        "phone":"0912345678",
        "password":"LongPass1234",
    })
    assert blocked.status_code == 429


def test_redis_rate_limit_is_shared_backend():
    class FakeRedis:
        def __init__(self):
            self.counts = defaultdict(int)

        def eval(self, _script, _keys, key, _ttl):
            self.counts[key] += 1
            return self.counts[key]

    redis = FakeRedis()
    first_request = SimpleNamespace(client=SimpleNamespace(host="203.0.113.1"), app=SimpleNamespace(state=SimpleNamespace(redis=redis)))
    second_request = SimpleNamespace(client=SimpleNamespace(host="203.0.113.2"), app=SimpleNamespace(state=SimpleNamespace(redis=redis)))
    enforce_rate_limit(first_request, "login", 1, identity="0912345678")
    with pytest.raises(HTTPException) as error:
        enforce_rate_limit(second_request, "login", 1, identity="0912345678")
    assert error.value.status_code == 429


def test_redis_failure_fails_closed():
    class UnavailableRedis:
        def eval(self, *_args):
            raise RedisError("offline")

    request = SimpleNamespace(
        client=SimpleNamespace(host="203.0.113.1"),
        app=SimpleNamespace(state=SimpleNamespace(redis=UnavailableRedis())),
    )
    with pytest.raises(HTTPException) as error:
        enforce_rate_limit(request, "login", 1)
    assert error.value.status_code == 503


def test_production_requires_redis_and_explicit_hosts(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("REDIS_URL", "")
    monkeypatch.setenv("ALLOWED_HOSTS", "example.com")
    with pytest.raises(RuntimeError, match="REDIS_URL"):
        Settings.from_environment()

    monkeypatch.setenv("REDIS_URL", "rediss://user:pass@localhost:6379/0")
    monkeypatch.setenv("ALLOWED_HOSTS", "*")
    with pytest.raises(RuntimeError, match="ALLOWED_HOSTS"):
        Settings.from_environment()

    monkeypatch.setenv("ALLOWED_HOSTS", "example.com")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@db.example/app?sslmode=verify-full")
    assert Settings.from_environment().production is True
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./telephone_sy.db")
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        Settings.from_environment()


def test_security_headers_and_host_validation(client):
    assert client.get("/readyz").json() == {"status":"ready"}
    response = client.get("/")
    assert response.status_code == 200
    policy = response.headers["content-security-policy"]
    assert "script-src 'self'" in policy
    assert "style-src 'self'" in policy
    assert "style-src-attr 'none'" in policy
    assert "unsafe-inline" not in policy
    assert response.headers["x-content-type-options"] == "nosniff"
    invalid_host = client.get("/", headers={"Host":"attacker.example"})
    assert invalid_host.status_code == 400


def test_request_body_limit_enforces_content_length():
    test_app = FastAPI()
    test_app.add_middleware(RequestBodyLimitMiddleware, maximum_bytes=4)

    @test_app.post("/")
    async def receive_body(request: Request):
        return {"size": len(await request.body())}

    test_client = TestClient(test_app)
    assert test_client.post("/", content=b"1234").status_code == 200
    assert test_client.post("/", content=b"12345").status_code == 413