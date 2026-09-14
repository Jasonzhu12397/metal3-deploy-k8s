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
from unittest.mock import patch

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
    """Uses kubevirt, not bgp-lb -- since enable_addon now (see
    api/addons.py's own docstring) rejects any addon without a real
    install method (INSTALL_METHODS) rather than accepting any catalog
    name, this needed to become one of the two addons that actually has
    one. bgp-lb itself is covered separately below."""
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
        kubevirt = next(a for a in r.json() if a["name"] == "kubevirt")
        assert kubevirt["enabled"] is False

        # enable -- mocks the actual Celery dispatch (.delay needs a real
        # broker this test suite has none of, same reasoning as every
        # other test in this project that touches a .delay() call);
        # what's under test here is enable_addon's own HTTP-layer
        # behavior (intent recorded, task triggered), not the task body
        # itself (that's tasks/test_addon_tasks.py's job).
        with patch("app.api.addons.install_addon_task.delay") as mock_delay:
            r = client.post(f"/api/v1/clusters/{cluster_id}/addons/kubevirt/enable", headers=headers)
        assert r.status_code == 200
        assert r.json() == {
            "cluster_id": cluster_id, "name": "kubevirt", "enabled": True, "install_triggered": True,
        }
        mock_delay.assert_called_once_with(cluster_id, "kubevirt")

        r = client.get(f"/api/v1/clusters/{cluster_id}/addons", headers=headers)
        kubevirt = next(a for a in r.json() if a["name"] == "kubevirt")
        assert kubevirt["enabled"] is True

        # other addons stay untouched
        license_mgr = next(a for a in r.json() if a["name"] == "license-manager")
        assert license_mgr["enabled"] is False

        # disable
        r = client.delete(f"/api/v1/clusters/{cluster_id}/addons/kubevirt/disable", headers=headers)
        assert r.status_code == 200
        assert r.json()["enabled"] is False

        r = client.get(f"/api/v1/clusters/{cluster_id}/addons", headers=headers)
        kubevirt = next(a for a in r.json() if a["name"] == "kubevirt")
        assert kubevirt["enabled"] is False


def test_enabling_an_addon_with_no_install_method_is_rejected_synchronously():
    """The actual gap this closes: before, enable_addon accepted ANY
    catalog addon name and only ever recorded intent -- clicking
    "enable" on something like bgp-lb (no real install method, see
    services/addons.py's own INSTALL_METHODS) would silently succeed
    while installing nothing, ever, discoverable only by noticing
    nothing happened. Now it's a clear, synchronous 400 at the moment
    you try, not a silent no-op."""
    asyncio.run(_reset())
    with TestClient(app) as client:
        headers = _login_headers(client)
        cluster_id = client.post(
            "/api/v1/clusters",
            json={"name": "addon-no-install-method-test", "control_plane_count": 1},
            headers=headers,
        ).json()["id"]

        with patch("app.api.addons.install_addon_task.delay") as mock_delay:
            r = client.post(f"/api/v1/clusters/{cluster_id}/addons/bgp-lb/enable", headers=headers)
        assert r.status_code == 400
        assert "no real install method" in r.json()["detail"]
        mock_delay.assert_not_called()

        # and it must not have recorded intent either -- a clean
        # rejection, not a partial one
        r = client.get(f"/api/v1/clusters/{cluster_id}/addons", headers=headers)
        bgp_lb = next(a for a in r.json() if a["name"] == "bgp-lb")
        assert bgp_lb["enabled"] is False


def test_list_addons_surfaces_real_install_status_once_set():
    """install_status/install_message come from Cluster.addon_status
    (written by tasks/addon_tasks.py, not this API layer) -- confirms
    list_cluster_addons actually reads and surfaces it rather than the
    schema field just existing unused."""
    asyncio.run(_reset())

    async def _seed_status(cluster_id: str) -> None:
        import uuid as uuid_mod
        from app.models.cluster import Cluster

        async with AsyncSessionLocal() as session:
            cluster = await session.get(Cluster, uuid_mod.UUID(cluster_id))
            cluster.addon_status = {"kubevirt": {"status": "installed", "message": "ok", "updated_at": "2026-01-01T00:00:00Z"}}
            await session.commit()

    with TestClient(app) as client:
        headers = _login_headers(client)
        cluster_id = client.post(
            "/api/v1/clusters",
            json={"name": "addon-status-test", "control_plane_count": 1},
            headers=headers,
        ).json()["id"]

        asyncio.run(_seed_status(cluster_id))

        r = client.get(f"/api/v1/clusters/{cluster_id}/addons", headers=headers)
        kubevirt = next(a for a in r.json() if a["name"] == "kubevirt")
        assert kubevirt["install_status"] == "installed"
        assert kubevirt["install_message"] == "ok"
        # an addon that was never attempted stays None, not some
        # misleading default
        kube_ovn = next(a for a in r.json() if a["name"] == "kube-ovn")
        assert kube_ovn["install_status"] is None


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
