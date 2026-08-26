"""
DELETE /clusters/{id} used to throw an unhandled IntegrityError as soon as
a cluster had any Deployment or NodePoolAssignment referencing it: those
foreign keys have no ON DELETE rule, and Postgres (unlike SQLite by
default) enforces them -- so this was invisible against the sqlite dev/test
database and would only have surfaced against the real docker-compose
Postgres. This test turns SQLite's FK enforcement on to reproduce that.
"""
import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete, event, select  # noqa: E402

from app.core.db import AsyncSessionLocal, engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.hardware_asset import AssetStatus, HardwareAsset  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.auth import hash_password  # noqa: E402

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "test-admin-password-123"

_fk_enabled = False


def _ensure_fk_enforcement() -> None:
    global _fk_enabled
    if _fk_enabled:
        return

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_fk(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    _fk_enabled = True


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


def test_deleting_a_cluster_with_assigned_hardware_releases_it_instead_of_500ing():
    _ensure_fk_enforcement()
    asyncio.run(_reset())

    with TestClient(app) as client:
        headers = _login_headers(client)

        cluster_id = client.post(
            "/api/v1/clusters",
            json={"name": "delete-me-cluster", "control_plane_count": 1},
            headers=headers,
        ).json()["id"]

        async def _seed_available_asset():
            async with AsyncSessionLocal() as session:
                asset = HardwareAsset(
                    name="delete-me-asset",
                    cpu_sockets=1,
                    cpu_cores_per_socket=4,
                    cpu_threads_per_core=1,
                    status=AssetStatus.AVAILABLE,
                )
                session.add(asset)
                await session.commit()
                await session.refresh(asset)
                return asset.id

        asset_id = str(asyncio.run(_seed_available_asset()))

        r = client.post(
            f"/api/v1/clusters/{cluster_id}/pools/pool1/assign",
            json={"asset_ids": [asset_id], "role": "worker"},
            headers=headers,
        )
        assert r.status_code == 201, r.text

        # this used to 500 with an unhandled IntegrityError
        r = client.delete(f"/api/v1/clusters/{cluster_id}", headers=headers)
        assert r.status_code == 204, r.text

        assert client.get(f"/api/v1/clusters/{cluster_id}", headers=headers).status_code == 404

        released = client.get(f"/api/v1/hardware-assets/{asset_id}", headers=headers).json()
        assert released["status"] == "available"
        assert released["cluster_id"] is None


def test_deleting_a_cluster_with_an_active_deployment_is_refused_not_crashed():
    _ensure_fk_enforcement()
    asyncio.run(_reset())

    with TestClient(app) as client:
        headers = _login_headers(client)

        cluster_id = client.post(
            "/api/v1/clusters",
            json={"name": "delete-me-cluster-2", "control_plane_count": 1},
            headers=headers,
        ).json()["id"]

        async def _seed_asset_and_active_deployment():
            from app.models.cluster import Cluster
            from app.models.deployment import Deployment, DeploymentPhase

            async with AsyncSessionLocal() as session:
                asset = HardwareAsset(
                    name="delete-me-asset-2",
                    cpu_sockets=1,
                    cpu_cores_per_socket=4,
                    cpu_threads_per_core=1,
                    status=AssetStatus.RESERVED,
                    cluster_id=uuid.UUID(cluster_id),
                    node_pool_name="pool1",
                )
                session.add(asset)
                cluster = await session.get(Cluster, uuid.UUID(cluster_id))
                deployment = Deployment(cluster_id=cluster.id, phase=DeploymentPhase.APPLYING_CLUSTER)
                session.add(deployment)
                await session.commit()

        asyncio.run(_seed_asset_and_active_deployment())

        r = client.delete(f"/api/v1/clusters/{cluster_id}", headers=headers)
        assert r.status_code == 409
        assert "in progress" in r.json()["detail"]

        # cluster must still exist -- the delete was refused, not half-applied
        assert client.get(f"/api/v1/clusters/{cluster_id}", headers=headers).status_code == 200
