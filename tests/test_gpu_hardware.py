"""
Covers GPU fields on HardwareAsset: create/patch/filter through the real
API, and that a GPU-homogeneous pool actually gets gpu=true/gpu-model
labels in the rendered CAPI manifest (the foundation any vLLM/GPU
workload deployment on top of this platform will need -- K8s has to know
which nodes actually have a GPU before anything can be scheduled onto
them).
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
from app.services.auth import hash_password  # noqa: E402
from app.services.asset_planner import AssetPlannerService  # noqa: E402

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


def test_create_and_filter_gpu_assets():
    asyncio.run(_reset())
    with TestClient(app) as client:
        headers = _login_headers(client)

        gpu_asset = client.post(
            "/api/v1/hardware-assets",
            json={
                "name": "gpu-node-01",
                "cpu_sockets": 2,
                "cpu_cores_per_socket": 32,
                "memory_gb": 512,
                "gpu_model": "NVIDIA H100 80GB",
                "gpu_count": 8,
                "gpu_memory_gb": 80,
            },
            headers=headers,
        ).json()
        assert gpu_asset["has_gpu"] is True
        assert gpu_asset["gpu_count"] == 8

        cpu_only_asset = client.post(
            "/api/v1/hardware-assets",
            json={"name": "cpu-node-01", "cpu_sockets": 2, "cpu_cores_per_socket": 32, "memory_gb": 256},
            headers=headers,
        ).json()
        assert cpu_only_asset["has_gpu"] is False
        assert cpu_only_asset["gpu_count"] == 0

        gpu_only = client.get("/api/v1/hardware-assets?has_gpu=true", headers=headers).json()
        gpu_only_names = {a["name"] for a in gpu_only}
        assert "gpu-node-01" in gpu_only_names
        assert "cpu-node-01" not in gpu_only_names

        cpu_only = client.get("/api/v1/hardware-assets?has_gpu=false", headers=headers).json()
        cpu_only_names = {a["name"] for a in cpu_only}
        assert "cpu-node-01" in cpu_only_names
        assert "gpu-node-01" not in cpu_only_names


def test_patch_can_set_gpu_fields_on_an_existing_asset():
    """Standard case: a node registered via BMH/Ironic inspection (which
    doesn't discover GPUs) needs GPU info filled in by hand afterward."""
    asyncio.run(_reset())
    with TestClient(app) as client:
        headers = _login_headers(client)
        asset = client.post(
            "/api/v1/hardware-assets",
            json={"name": "node-01", "cpu_sockets": 2, "cpu_cores_per_socket": 32, "memory_gb": 256},
            headers=headers,
        ).json()
        assert asset["has_gpu"] is False

        r = client.patch(
            f"/api/v1/hardware-assets/{asset['id']}",
            json={"gpu_model": "NVIDIA A100 40GB", "gpu_count": 4, "gpu_memory_gb": 40},
            headers=headers,
        )
        assert r.status_code == 200
        updated = r.json()
        assert updated["has_gpu"] is True
        assert updated["gpu_model"] == "NVIDIA A100 40GB"
        assert updated["gpu_count"] == 4


def _asset(**kw):
    from app.models.hardware_asset import HardwareAsset

    defaults = dict(
        name="gpu-01",
        cpu_sockets=2,
        cpu_cores_per_socket=32,
        cpu_threads_per_core=2,
        memory_gb=512,
        gpu_model="NVIDIA H100 80GB",
        gpu_count=8,
        gpu_memory_gb=80,
    )
    defaults.update(kw)
    return HardwareAsset(**defaults)


def _assignment(**kw):
    from types import SimpleNamespace

    defaults = dict(
        role="worker",
        reserved_cores_per_socket=4,
        cpu_manager_policy="static",
        topology_manager_policy="single-numa-node",
        isolation_interrupts=False,
        hugepage_type="1GB",
        hugepage_count_1gb=16,
        hugepage_count_2mb=0,
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def test_gpu_homogeneous_pool_gets_labeled_in_rendered_manifest():
    planner = AssetPlannerService()
    gpu_asset_1 = _asset(name="gpu-01")
    gpu_asset_2 = _asset(name="gpu-02")
    assignment_1 = _assignment()
    assignment_2 = _assignment()

    entry = planner.build_worker_pool_entry("gpu-pool", [gpu_asset_1, gpu_asset_2], [assignment_1, assignment_2])
    assert "gpu=true" in entry["node_labels"]
    assert "gpu-model=NVIDIA_H100_80GB" in entry["node_labels"]  # spaces replaced -- K8s label values can't have them
    assert entry["gpu_count_per_node"] == 8


def test_mixed_gpu_and_non_gpu_pool_does_not_falsely_label_gpu():
    """A pool's node_labels apply to the whole MachineDeployment -- if even
    one node in the pool lacks a GPU, labeling the pool gpu=true would be
    a lie that could get a GPU-requiring pod scheduled onto a node with no
    GPU at all."""
    planner = AssetPlannerService()
    gpu_asset = _asset(name="gpu-01")
    cpu_asset = _asset(name="cpu-01", gpu_model=None, gpu_count=0, gpu_memory_gb=None)
    assignment_1 = _assignment()
    assignment_2 = _assignment()

    entry = planner.build_worker_pool_entry("mixed-pool", [gpu_asset, cpu_asset], [assignment_1, assignment_2])
    assert "gpu=true" not in entry["node_labels"]
    assert entry["gpu_count_per_node"] == 0
