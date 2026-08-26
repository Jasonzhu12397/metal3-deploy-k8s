"""
Exercises POST /hardware-assets/{id}/sync-from-ironic through the real HTTP
layer -- both with and without the optional `ironic_inventory` body. The
with-body path used to silently do nothing: the endpoint declared
`ironic_inventory: dict | None = None` as a bare (non-Pydantic) body
parameter, which FastAPI does NOT embed under its parameter name for a
single body param -- so the documented/frontend-sent shape of
`{"ironic_inventory": {...}}` never actually reached the parameter, it
just silently stayed None and the enrichment step was skipped. No error,
no warning -- it just quietly did less than it claimed to. This test
would have caught it.
"""
import asyncio
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.core.db import AsyncSessionLocal, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.auth import hash_password  # noqa: E402

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "test-admin-password-123"

MOCK_BMH_HARDWARE = {
    "cpu": {"model": "Intel", "count": 4},
    "ramMebibytes": 8192,
    "nics": [],
    "storage": [],
    "systemVendor": {"manufacturer": "Dell", "productName": "R660", "serialNumber": "S1"},
}


async def _reset_admin_user() -> None:
    await init_db()
    async with AsyncSessionLocal() as session:
        from sqlalchemy import delete

        await session.execute(delete(User))
        session.add(User(username=ADMIN_USERNAME, hashed_password=hash_password(ADMIN_PASSWORD)))
        await session.commit()


def _login_headers(client: TestClient) -> dict[str, str]:
    r = client.post("/api/v1/auth/login", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_sync_from_ironic_with_wrapped_inventory_body_actually_applies_it():
    asyncio.run(_reset_admin_user())

    with patch("app.services.kubernetes.KubernetesService._ensure_loaded", return_value=None), \
         patch("app.services.bmc.BMCService.store_credentials", return_value="x-bmc-secret"), \
         patch(
             "app.services.metal3.Metal3Service.register_host",
             return_value={"metadata": {"resourceVersion": "1"}},
         ), \
         patch("app.services.metal3.Metal3Service.get_hardware_details", return_value=MOCK_BMH_HARDWARE):
        with TestClient(app) as client:
            headers = _login_headers(client)

            client.post(
                "/api/v1/baremetalhosts",
                json={
                    "name": "sync-test",
                    "node_pool_name": "pool1",
                    "bmc_address": "redfish://x",
                    "boot_mac_address": "aa:bb:cc:dd:ee:01",
                    "credentials": {"username": "a", "password": "b"},
                },
                headers=headers,
            )
            asset_id = next(
                a["id"]
                for a in client.get("/api/v1/hardware-assets", headers=headers).json()
                if a["name"] == "sync-test"
            )

            inventory = {
                "cpu": {"count": 8, "socket_count": 1},
                "memory": {"physical_mb": 16384},
                "interfaces": [{"name": "eno1", "pci_address": "0000:01:00.0", "numa_node": 0}],
                "disks": [{"name": "/dev/nvme0n1", "model": "Test NVMe", "size": 1_000_000_000}],
            }

            r = client.post(
                f"/api/v1/hardware-assets/{asset_id}/sync-from-ironic",
                json={"ironic_inventory": inventory},
                headers=headers,
            )
            assert r.status_code == 200
            nics = r.json()["nics"]
            assert any(n["pci_address"] == "0000:01:00.0" for n in nics), (
                "wrapped ironic_inventory body did not reach the endpoint"
            )

            # the common case (no body at all) must keep working too
            r2 = client.post(f"/api/v1/hardware-assets/{asset_id}/sync-from-ironic", headers=headers)
            assert r2.status_code == 200
