"""Tests run against a separate `wasp_test` database and bucket so they never touch dev data.

The environment is rewritten before any `app` import, because settings are cached on first use.
"""

import os

_base_url = os.environ.get(
    "WASP_DATABASE_URL", "postgresql+psycopg://wasp:wasp@localhost:5432/wasp"
)
_server_url, _, _ = _base_url.rpartition("/")
os.environ["WASP_DATABASE_URL"] = f"{_server_url}/wasp_test"
os.environ["WASP_S3_BUCKET"] = "wasp-test"
os.environ["WASP_CELERY_EAGER"] = "true"  # run document processing inline

from collections.abc import Callable, Iterator  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from app.auth import create_access_token, hash_password  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base, Institution, User  # noqa: E402
from app.models.enums import UserRole  # noqa: E402
from app.rules.engine import sync_rules  # noqa: E402
from app.storage import ensure_bucket  # noqa: E402

PASSWORD = "test-password"


@pytest.fixture(scope="session", autouse=True)
def test_database() -> None:
    admin = create_engine(f"{_server_url}/postgres", isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        if not conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = 'wasp_test'")):
            conn.execute(text("CREATE DATABASE wasp_test"))
    admin.dispose()
    command.upgrade(Config("alembic.ini"), "head")
    ensure_bucket()


@pytest.fixture(autouse=True)
def clean_tables() -> Iterator[None]:
    with SessionLocal() as db:
        sync_rules(db)  # rules are reference data; tests (e.g. verification) may change them
    yield
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} CASCADE"))


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def make_institution() -> Callable[..., Institution]:
    counter = iter(range(1, 10_000))

    def _make(name: str = "Test Institute") -> Institution:
        with SessionLocal() as db:
            institution = Institution(name=name, aicte_id=f"TEST-{next(counter):04d}")
            db.add(institution)
            db.commit()
            return institution

    return _make


@pytest.fixture
def make_user(make_institution) -> Callable[..., User]:
    counter = iter(range(1, 10_000))

    def _make(
        role: UserRole = UserRole.REVIEWER,
        is_active: bool = True,
        institution: Institution | None = None,
    ) -> User:
        if role == UserRole.INSTITUTION and institution is None:
            institution = make_institution()
        with SessionLocal() as db:
            user = User(
                email=f"{role.value}-{next(counter)}@test.dev",
                full_name="Test User",
                password_hash=hash_password(PASSWORD),
                role=role,
                is_active=is_active,
                institution_id=institution.id if institution else None,
            )
            db.add(user)
            db.commit()
            return user

    return _make


def auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user)}"}
