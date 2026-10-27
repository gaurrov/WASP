from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.auth import require_roles
from app.main import app
from app.models.enums import UserRole
from tests.conftest import PASSWORD


def login(client: TestClient, email: str, password: str = PASSWORD):
    return client.post("/api/auth/login", data={"username": email, "password": password})


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok", "database": "ok"}


def test_login_and_me(client, make_user):
    user = make_user(UserRole.INSTITUTION)
    token = login(client, user.email).json()["access_token"]

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert me.status_code == 200
    assert me.json()["email"] == user.email
    assert me.json()["role"] == "institution"


def test_login_rejects_wrong_password(client, make_user):
    user = make_user()
    assert login(client, user.email, "wrong").status_code == 401


def test_login_rejects_inactive_user(client, make_user):
    user = make_user(is_active=False)
    assert login(client, user.email).status_code == 401


def test_me_requires_valid_token(client):
    assert client.get("/api/auth/me").status_code == 401
    bad = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert bad.status_code == 401


def test_require_roles(make_user):
    probe = FastAPI()

    @probe.get("/admin-only")
    def admin_only(_: Annotated[object, Depends(require_roles(UserRole.ADMIN))]):
        return {"ok": True}

    probe.include_router(app.router)
    client = TestClient(probe)
    reviewer, admin = make_user(UserRole.REVIEWER), make_user(UserRole.ADMIN)

    def call(user):
        token = login(client, user.email).json()["access_token"]
        return client.get("/admin-only", headers={"Authorization": f"Bearer {token}"})

    assert call(reviewer).status_code == 403
    assert call(admin).status_code == 200
