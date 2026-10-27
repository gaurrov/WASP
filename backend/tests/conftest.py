import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.auth import hash_password
from app.db import SessionLocal
from app.main import app
from app.models import User
from app.models.enums import UserRole

PASSWORD = "test-password"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def make_user() -> Iterator:
    created: list[uuid.UUID] = []

    def _make(role: UserRole = UserRole.REVIEWER, is_active: bool = True) -> User:
        with SessionLocal() as db:
            user = User(
                email=f"test-{uuid.uuid4().hex[:8]}@wasp.dev",
                full_name="Test User",
                password_hash=hash_password(PASSWORD),
                role=role,
                is_active=is_active,
            )
            db.add(user)
            db.commit()
            created.append(user.id)
            return user

    yield _make

    with SessionLocal() as db:
        for user_id in created:
            db.delete(db.get(User, user_id))
        db.commit()
