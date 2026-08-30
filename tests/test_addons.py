"""
Covers GET /addons/catalog, GET/enable/disable on
/clusters/{id}/addons -- this had zero test coverage before despite being
a real, wired-up feature (found while renaming a few catalog entries away
from names lifted directly from a specific customer's config; this test
would have caught it if that rename had broken anything).
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete  # noqa: E402

from app.core.db import AsyncSessionLocal, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.addon_catalog import ADDON_CATALOG  # noqa: E402
from app.services.auth import hash_password  # noqa: E402

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "test-admin-password-123"


async def _reset() -> None:
    await init_db()
    async with AsyncSessionLocal() as session:
        await session.execute(delete(User))
        session.add(User(username=ADMIN_USERNAME, hashed_password=hash_password(ADMIN_PASSWORD)))
        await session.commit()


def _login_headers(client: TestClient) -> dict[str, str]:
    r = client.post("/api/v1/auth/login", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_catalog_is_cluster_agnostic_and_generically_named():
    """Also guards against re-introducing a customer-specific name into
    the catalog -- every entry's `name` should read as a generic
    technical identifier, not a product/customer brand."""
    asyncio.run(_reset())
    with TestClient(app) as client:
        headers = _login_headers(client)
        r = client.get("/api/v1/addons/catalog", headers=headers)
        assert r.status_code == 200
        items = r.json()
        assert len(items) == len(ADDON_CATALOG)
        names = {i["name"] for i in items}
        # the three names this was specifically renamed away from
        assert "ecfe" not in names
        assert "ccd-licensing" not in names
        assert "pm_webhook_snmp" not in names
        assert {"bgp-lb", "license-manager", "snmp-alert-forwarder"} <= names
        # cluster-agnostic catalog never has an `enabled` key that means anything
        assert all("enabled" not in i or i["enabled"] is False for i in items)


def test_enable_and_disable_round_trip():
    asyncio.run(_reset())
    with TestClient(app) as client:
        headers = _login_headers(client)
        cluster_id = client.post(
            "/api/v1/clusters",
            json={"name": "addon-test-cluster", "control_plane_count": 1},
            headers=headers,
        ).json()["id"]

        # starts disabled
        r = client.get(f"/api/v1/clusters/{cluster_id}/addons", headers=headers)
        assert r.status_code == 200
        bgp_lb = next(a for a in r.json() if a["name"] == "bgp-lb")
        assert bgp_lb["enabled"] is False

        # enable
        r = client.post(f"/api/v1/clusters/{cluster_id}/addons/bgp-lb/enable", headers=headers)
        assert r.status_code == 200
        assert r.json() == {"cluster_id": cluster_id, "name": "bgp-lb", "enabled": True}

        r = client.get(f"/api/v1/clusters/{cluster_id}/addons", headers=headers)
        bgp_lb = next(a for a in r.json() if a["name"] == "bgp-lb")
        assert bgp_lb["enabled"] is True

        # other addons stay untouched
        license_mgr = next(a for a in r.json() if a["name"] == "license-manager")
        assert license_mgr["enabled"] is False

        # disable
        r = client.delete(f"/api/v1/clusters/{cluster_id}/addons/bgp-lb/disable", headers=headers)
        assert r.status_code == 200
        assert r.json()["enabled"] is False

        r = client.get(f"/api/v1/clusters/{cluster_id}/addons", headers=headers)
        bgp_lb = next(a for a in r.json() if a["name"] == "bgp-lb")
        assert bgp_lb["enabled"] is False


def test_enabling_unknown_addon_is_rejected():
    asyncio.run(_reset())
    with TestClient(app) as client:
        headers = _login_headers(client)
        cluster_id = client.post(
            "/api/v1/clusters",
            json={"name": "addon-test-cluster-2", "control_plane_count": 1},
            headers=headers,
        ).json()["id"]

        r = client.post(f"/api/v1/clusters/{cluster_id}/addons/totally-made-up-addon/enable", headers=headers)
        assert r.status_code == 404
