import os

os.environ.setdefault("SECRET_KEY", "test-key-for-isolated-test-sessions-only")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import password_hash
from database import Base, get_db
from main import app
from models import User
from services.rate_limit import clear_memory_rate_limits


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    app.state.test_session_factory = session_factory

    def override_get_db():
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    from routers import listings

    monkeypatch.setattr(listings, "UPLOAD_DIR", tmp_path)
    clear_memory_rate_limits()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    del app.state.test_session_factory
    Base.metadata.drop_all(engine)
    engine.dispose()


def register(client: TestClient, phone: str = "0912345678", name: str = "مستخدم"):
    response = client.post("/api/auth/register", json={
        "name": name,
        "phone": phone,
        "password": "LongPass1234",
        "city": "دمشق",
    })
    assert response.status_code == 201, response.text
    assert response.json()["role"] == "user"
    return response.json()


def login(client: TestClient, phone: str = "0912345678"):
    return client.post("/api/auth/login", json={"phone": phone, "password": "LongPass1234"})


def make_admin(client):
    response = register(client, "0999999999", "مشرف")
    from database import get_db as original_dependency

    override = app.dependency_overrides[original_dependency]
    db = next(override())
    user = db.get(User, response["id"])
    user.role = "admin"
    db.commit()
    db.close()
    return response


def create_listing(client, **changes):
    payload = {
        "brand": "Apple",
        "model": "iPhone 15",
        "price": "750",
        "currency": "USD",
        "city": "دمشق",
        "condition": "used",
        "description": "وصف الجهاز",
        "seller_name": "بائع",
        "contact_phone": "0912345678",
        "storage_gb": 256,
    }
    payload.update(changes)
    return client.post("/api/listings", json=payload)