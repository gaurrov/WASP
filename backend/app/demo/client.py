"""A small client for the running API, used by the demo scripts. It talks HTTP to the real stack
(API, worker, beat) so a rehearsal exercises exactly what the audience will see."""

import os
import time
from collections.abc import Callable
from typing import Any

import httpx

from app.seed import DEMO_PASSWORD

API = os.environ.get("WASP_DEMO_API", "http://localhost:8000/api")
ACCOUNTS = {
    "institution": "institution@wasp.dev",
    "reviewer": "reviewer@wasp.dev",
    "admin": "admin@wasp.dev",
}


class DemoError(AssertionError):
    pass


class Client:
    def __init__(self, role: str):
        self.role = role
        self.http = httpx.Client(base_url=API, timeout=60)
        res = self.http.post(
            "/auth/login", data={"username": ACCOUNTS[role], "password": DEMO_PASSWORD}
        )
        if res.status_code != 200:
            raise DemoError(f"login as {role} failed: {res.status_code} {res.text}")
        self.http.headers["Authorization"] = f"Bearer {res.json()['access_token']}"

    def _check(self, res: httpx.Response, expect: int | tuple[int, ...]) -> Any:
        ok = (expect,) if isinstance(expect, int) else expect
        if res.status_code not in ok:
            raise DemoError(
                f"{res.request.method} {res.request.url.path} → {res.status_code}: {res.text}"
            )
        return (
            res.json()
            if res.content and res.headers.get("content-type", "").startswith("application/json")
            else None
        )

    def get(self, path: str, **params) -> Any:
        return self._check(self.http.get(path, params=params), 200)

    def post(
        self, path: str, json: Any = None, expect: int | tuple[int, ...] = (200, 201, 202)
    ) -> Any:
        return self._check(self.http.post(path, json=json), expect)

    def upload(
        self, app_id: str, filename: str, data: bytes, doc_type: str, replaces_id: str | None = None
    ) -> Any:
        form = {"doc_type": doc_type} | ({"replaces_id": replaces_id} if replaces_id else {})
        res = self.http.post(
            f"/applications/{app_id}/documents",
            files={"file": (filename, data, "application/pdf")},
            data=form,
        )
        return self._check(res, 201)


def wait_until(
    what: str, check: Callable[[], Any], timeout: float = 120, interval: float = 0.5
) -> Any:
    """Poll until `check()` returns something truthy; the worker does the real work async."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if result := check():
            return result
        time.sleep(interval)
    raise DemoError(f"timed out after {timeout:.0f}s waiting for {what}")
