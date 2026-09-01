"""
Covers ClusterCreate's _cloud_providers_need_a_machine_spec validator --
untested before this, which is exactly how it shipped requiring
control_plane_flavor/control_plane_image for the docker (CAPD) provider
too, when CAPD explicitly needs neither (DockerMachineTemplate has no
such fields -- see templates/capi/providers/docker.yaml.j2). A real user
hit this: creating a docker-provider cluster with the frontend's
(correctly) hidden flavor/image fields 422'd, and a separate frontend bug
(fixed alongside this) rendered that error as the literal string
"[object Object]" instead of the actual message, making it doubly
confusing.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from app.schemas.cluster import ClusterCreate  # noqa: E402


def test_metal3_does_not_need_flavor_or_image():
    c = ClusterCreate(name="x", infrastructure_provider="metal3", control_plane_count=3)
    assert c.control_plane_flavor is None


def test_docker_does_not_need_flavor_or_image():
    """The actual bug: this used to raise, blocking every CAPD cluster
    creation through the frontend (which correctly never sends these
    fields for docker in the first place)."""
    c = ClusterCreate(
        name="test1",
        namespace="metal3",
        infrastructure_provider="docker",
        control_plane_count=3,
        control_plane_endpoint="192.168.1.2",
        spec={"pod_cidr": "192.168.0.0/16", "service_cidr": "10.96.0.0/12", "k8s_version": "v1.29.0"},
    )
    assert c.infrastructure_provider.value == "docker"


@pytest.mark.parametrize("provider", ["openstack", "vsphere", "kubevirt"])
def test_real_cloud_providers_still_require_flavor_and_image(provider):
    """The fix must not accidentally exempt every non-metal3 provider --
    only docker, which genuinely has no use for these fields. openstack/
    vsphere/kubevirt are real infrastructure that needs to know what to
    boot."""
    with pytest.raises(ValidationError, match="needs control_plane_flavor and control_plane_image"):
        ClusterCreate(name="x", infrastructure_provider=provider, control_plane_count=1)


@pytest.mark.parametrize("provider", ["openstack", "vsphere", "kubevirt"])
def test_real_cloud_providers_succeed_with_flavor_and_image(provider):
    c = ClusterCreate(
        name="x",
        infrastructure_provider=provider,
        control_plane_count=1,
        control_plane_flavor="m1.large",
        control_plane_image="ubuntu-22.04",
    )
    assert c.control_plane_flavor == "m1.large"


def test_docker_worker_pool_also_does_not_need_flavor_or_image():
    c = ClusterCreate(
        name="x",
        infrastructure_provider="docker",
        control_plane_count=1,
        worker_pools=[{"name": "workers", "count": 2}],
    )
    assert c.worker_pools[0].count == 2


def test_openstack_worker_pool_still_requires_flavor_and_image():
    with pytest.raises(ValidationError, match="needs flavor and image"):
        ClusterCreate(
            name="x",
            infrastructure_provider="openstack",
            control_plane_count=1,
            control_plane_flavor="m1.large",
            control_plane_image="ubuntu-22.04",
            worker_pools=[{"name": "workers", "count": 2}],
        )


def test_create_docker_cluster_through_the_real_api_endpoint():
    """Schema-level validation passing isn't the same as the actual HTTP
    request succeeding -- this is the exact payload shape the frontend's
    create-cluster form sends for a docker/CAPD cluster, through the real
    FastAPI endpoint, confirming the fix actually resolves the reported
    422."""
    import asyncio

    os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
    from fastapi.testclient import TestClient
    from sqlalchemy import delete
    from app.core.db import AsyncSessionLocal, init_db
    from app.main import app
    from app.models.cluster import Cluster
    from app.models.user import User
    from app.services.auth import hash_password

    async def _reset():
        await init_db()
        async with AsyncSessionLocal() as session:
            await session.execute(delete(User))
            await session.execute(delete(Cluster))
            session.add(User(username="admin", hashed_password=hash_password("test-password-123")))
            await session.commit()

    asyncio.run(_reset())

    with TestClient(app) as client:
        login = client.post("/api/v1/auth/login", json={"username": "admin", "password": "test-password-123"})
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        r = client.post(
            "/api/v1/clusters",
            json={
                "name": "test1",
                "namespace": "metal3",
                "infrastructure_provider": "docker",
                "control_plane_count": 3,
                "control_plane_endpoint": "192.168.1.2",
                "spec": {"pod_cidr": "192.168.0.0/16", "service_cidr": "10.96.0.0/12", "k8s_version": "v1.29.0"},
            },
            headers=headers,
        )
        assert r.status_code == 201, r.text
        assert r.json()["infrastructure_provider"] == "docker"
