"""
Covers GET /api/v1/machines -- found via the same module-coverage
cross-reference as tests/test_introspection.py and
tests/test_cloud_planner.py to have zero tests referencing it, despite
being a real, registered (app.main includes machines.router), reachable
endpoint that queries live CAPI Machine objects for a cluster.
"""
import asyncio
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")

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


def _login_headers(client: TestClient) -> dict[str, str]:
    r = client.post("/api/v1/auth/login", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_list_machines_requires_auth():
    asyncio.run(_reset_admin_user())
    with TestClient(app) as client:
        r = client.get("/api/v1/machines", params={"cluster_name": "my-cluster"})
        assert r.status_code == 401


def test_list_machines_requires_cluster_name_query_param():
    """cluster_name has no default -- omitting it must be a clean 422,
    not a 500 from an unrelated code path."""
    asyncio.run(_reset_admin_user())
    with TestClient(app) as client:
        headers = _login_headers(client)
        r = client.get("/api/v1/machines", headers=headers)
        assert r.status_code == 422


def test_list_machines_filters_by_cluster_name_label_selector():
    """Confirms the actual CAPI convention this project relies on
    elsewhere too: Machines get selected via the
    cluster.x-k8s.io/cluster-name label, not by owner reference or name
    prefix matching."""
    asyncio.run(_reset_admin_user())
    fake_machines = [
        {"metadata": {"name": "my-cluster-control-plane-abc12"}, "status": {"phase": "Running"}},
        {"metadata": {"name": "my-cluster-workers-xyz89"}, "status": {"phase": "Provisioning"}},
    ]
    with TestClient(app) as client:
        headers = _login_headers(client)
        with patch("app.api.machines.capi_service.list_machines", return_value=fake_machines) as mock_list:
            r = client.get(
                "/api/v1/machines",
                params={"cluster_name": "my-cluster", "namespace": "metal3"},
                headers=headers,
            )
        assert r.status_code == 200
        assert r.json() == fake_machines
        mock_list.assert_called_once_with("my-cluster", "metal3")


def test_list_machines_defaults_namespace_to_metal3():
    asyncio.run(_reset_admin_user())
    with TestClient(app) as client:
        headers = _login_headers(client)
        with patch("app.api.machines.capi_service.list_machines", return_value=[]) as mock_list:
            r = client.get("/api/v1/machines", params={"cluster_name": "my-cluster"}, headers=headers)
        assert r.status_code == 200
        mock_list.assert_called_once_with("my-cluster", "metal3")


def test_list_machines_returns_empty_list_for_a_cluster_with_no_machines_yet():
    """A cluster whose Machine objects haven't been created yet (early
    in deployment) must return an empty list, not an error."""
    asyncio.run(_reset_admin_user())
    with TestClient(app) as client:
        headers = _login_headers(client)
        with patch("app.api.machines.capi_service.list_machines", return_value=[]):
            r = client.get("/api/v1/machines", params={"cluster_name": "brand-new-cluster"}, headers=headers)
        assert r.status_code == 200
        assert r.json() == []
