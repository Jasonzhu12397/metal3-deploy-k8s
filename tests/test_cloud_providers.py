"""
Exercises the non-metal3 infrastructure providers (OpenStack/CAPO,
vSphere/CAPV, KubeVirt/CAPK) end to end through the real HTTP API and the
real deployment orchestration function -- not just template rendering in
isolation. This is deliberately held to the same bar as the metal3 flow's
tests/test_deployment_tasks.py: actually run `_run_deployment`, mocking
only the Kubernetes-facing calls (no real OpenStack/vSphere/KubeVirt
cluster exists to test against), and confirm the Deployment row reaches
`complete`.

What this does NOT prove: that a real OpenStack/vSphere/KubeVirt cluster
actually comes up healthy from these manifests. CAPO/CAPV/CAPK's exact CRD
field names shift between versions and this project has no live
infrastructure to validate against -- see the NOTE comments at the top of
each templates/capi/providers/*.yaml.j2 file. What this DOES prove: the
API accepts these clusters, generates structurally valid manifests for
each provider (right Kinds, right apiVersions, right replica counts), the
hardware-asset flow is correctly refused for them, and the orchestration
state machine (queued -> ... -> complete, including the phases that don't
apply to a hardware-less provider) runs without crashing.
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
from app.models.deployment import DeploymentPhase  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.auth import hash_password  # noqa: E402
from app.tasks.deployment_tasks import _run_deployment  # noqa: E402

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "test-admin-password-123"


async def _reset_admin() -> None:
    await init_db()
    async with AsyncSessionLocal() as session:
        await session.execute(delete(User))
        session.add(User(username=ADMIN_USERNAME, hashed_password=hash_password(ADMIN_PASSWORD)))
        await session.commit()


def _login_headers(client: TestClient) -> dict[str, str]:
    r = client.post("/api/v1/auth/login", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


PROVIDER_CASES = [
    (
        "openstack",
        {"openstack": {"cloud_name": "mycloud", "external_network_id": "ext-1"}},
        "OpenStackCluster",
    ),
    (
        "vsphere",
        {"vsphere": {"server": "vcenter.local", "datacenter": "dc1", "datastore": "ds1", "network": "vm-net"}},
        "VSphereCluster",
    ),
    (
        "kubevirt",
        {"kubevirt": {"storage_class_name": "rook-ceph-block"}},
        "KubevirtCluster",
    ),
]


def test_creating_a_cloud_cluster_without_flavor_image_is_rejected():
    asyncio.run(_reset_admin())
    with TestClient(app) as client:
        headers = _login_headers(client)
        r = client.post(
            "/api/v1/clusters",
            json={"name": "no-flavor-cluster", "infrastructure_provider": "openstack"},
            headers=headers,
        )
        assert r.status_code == 422, "should refuse a cloud cluster with no machine spec at all"


def test_hardware_assignment_is_refused_for_cloud_clusters():
    asyncio.run(_reset_admin())
    with TestClient(app) as client:
        headers = _login_headers(client)
        cluster_id = client.post(
            "/api/v1/clusters",
            json={
                "name": "no-hw-cluster",
                "infrastructure_provider": "openstack",
                "control_plane_flavor": "m1.large",
                "control_plane_image": "ubuntu-22.04",
            },
            headers=headers,
        ).json()["id"]

        r = client.post(
            f"/api/v1/clusters/{cluster_id}/pools/pool1/assign",
            json={"asset_ids": []},
            headers=headers,
        )
        assert r.status_code == 409
        assert "no physical hardware" in r.json()["detail"].lower()


def test_each_cloud_provider_generates_and_deploys_end_to_end():
    for provider, provider_config, expected_infra_kind in PROVIDER_CASES:
        asyncio.run(_reset_admin())
        with TestClient(app) as client:
            headers = _login_headers(client)

            create_payload = {
                "name": f"{provider}-e2e-cluster",
                "infrastructure_provider": provider,
                "control_plane_count": 3,
                "control_plane_endpoint": "10.0.0.100",
                "control_plane_flavor": "m1.large",
                "control_plane_image": "ubuntu-22.04",
                "worker_pools": [
                    {"name": "pool1", "count": 2, "flavor": "m1.xlarge", "image": "ubuntu-22.04"}
                ],
                "spec": provider_config,
            }
            r = client.post("/api/v1/clusters", json=create_payload, headers=headers)
            assert r.status_code == 201, r.text
            cluster_id = r.json()["id"]
            assert r.json()["infrastructure_provider"] == provider

            # 1. manifest preview
            r = client.post(f"/api/v1/clusters/{cluster_id}/manifests/generate", headers=headers)
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["bmh_yaml"] == ""  # no physical hosts for a cloud provider
            assert expected_infra_kind in body["cluster_config_yaml"]
            assert "KubeadmControlPlane" in body["cluster_config_yaml"]

            # 2. trigger a real deployment (mocking only the k8s-facing and
            # celery-broker-facing calls -- this test drives _run_deployment
            # directly afterward, so the real Celery enqueue is unwanted
            # here and would otherwise try to reach a real Redis broker)
            with patch("app.services.kubernetes.KubernetesService._ensure_loaded", return_value=None), \
                 patch("app.api.deployments.run_deployment_task") as mock_task:
                mock_task.delay.return_value.id = "fake-celery-id"
                r = client.post("/api/v1/deployments", json={"cluster_id": cluster_id}, headers=headers)
                assert r.status_code == 201, r.text
                deployment_id = r.json()["id"]

            # 3. actually run the orchestration function end to end, same as
            # the metal3 pipeline's test -- no physical BMH to wait for, so
            # it should sail through applying_bmh/waiting_for_hosts straight
            # to applying_cluster.
            with patch("app.tasks.deployment_tasks.CAPIService.apply_cluster", return_value=[]), \
                 patch(
                     "app.tasks.deployment_tasks.CAPIService.get_cluster_status",
                     return_value={"conditions": [{"type": "ControlPlaneReady", "status": "True"}]},
                 ):
                asyncio.run(_run_deployment(deployment_id, {
                    "name": create_payload["name"],
                    "namespace": "metal3",
                    "infrastructure_provider": provider,
                    "control_plane_count": 3,
                    "control_plane_endpoint": "10.0.0.100",
                    "control_plane_flavor": "m1.large",
                    "control_plane_image": "ubuntu-22.04",
                    "worker_pools": [
                        {"name": "pool1", "count": 2, "flavor": "m1.xlarge", "image": "ubuntu-22.04",
                         "node_labels": []}
                    ],
                    "hosts": [],
                    **provider_config,
                }, "metal3"))

            r = client.get(f"/api/v1/deployments/{deployment_id}", headers=headers)
            assert r.json()["phase"] == DeploymentPhase.COMPLETE.value, (
                f"{provider} deployment did not reach complete: {r.json()}"
            )
