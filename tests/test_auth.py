"""
Login, protected-route enforcement, and password change -- exercised
against the real app/DB stack (not mocked), reusing whatever sqlite file
conftest.py points DATABASE_URL at. Since the DB engine is bound at import
time (see app/core/db.py) and shared across the whole pytest session, this
resets the `users` table itself rather than relying on the app's
first-boot-only seeding, so it doesn't matter what other test modules did
to that table first.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete  # noqa: E402

from app.core.db import AsyncSessionLocal, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.auth import hash_password  # noqa: E402

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "test-admin-password-123"


async def _reset_admin_user() -> None:
    await init_db()
    async with AsyncSessionLocal() as session:
        await session.execute(delete(User))
        session.add(User(username=ADMIN_USERNAME, hashed_password=hash_password(ADMIN_PASSWORD)))
        await session.commit()


def test_protected_routes_require_a_token():
    asyncio.run(_reset_admin_user())
    with TestClient(app) as client:
        assert client.get("/api/v1/clusters").status_code == 401
        assert client.get("/api/v1/hardware-assets").status_code == 401
        # health stays open
        assert client.get("/healthz").status_code == 200


def test_login_rejects_wrong_password():
    asyncio.run(_reset_admin_user())
    with TestClient(app) as client:
        r = client.post("/api/v1/auth/login", json={"username": ADMIN_USERNAME, "password": "nope"})
        assert r.status_code == 401


def test_full_login_and_change_password_flow():
    asyncio.run(_reset_admin_user())
    with TestClient(app) as client:
        r = client.post(
            "/api/v1/auth/login", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD}
        )
        assert r.status_code == 200
        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # token actually authorizes a protected route now
        r = client.get("/api/v1/clusters", headers=headers)
        assert r.status_code == 200

        r = client.get("/api/v1/auth/me", headers=headers)
        assert r.json()["username"] == ADMIN_USERNAME

        # wrong current_password is rejected
        r = client.post(
            "/api/v1/auth/change-password",
            headers=headers,
            json={"current_password": "wrong", "new_password": "brand-new-password-1"},
        )
        assert r.status_code == 401

        # correct change goes through
        r = client.post(
            "/api/v1/auth/change-password",
            headers=headers,
            json={"current_password": ADMIN_PASSWORD, "new_password": "brand-new-password-1"},
        )
        assert r.status_code == 204

        # old password no longer works, new one does
        r = client.post(
            "/api/v1/auth/login", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD}
        )
        assert r.status_code == 401
        r = client.post(
            "/api/v1/auth/login",
            json={"username": ADMIN_USERNAME, "password": "brand-new-password-1"},
        )
        assert r.status_code == 200
