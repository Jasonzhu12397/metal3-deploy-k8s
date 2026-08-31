"""
Covers POST/GET/DELETE /ai-workloads and the redeploy endpoint -- the
target-cluster Kubernetes calls (services/target_cluster.py's
get_client_for_cluster/apply_deployment_and_service/delete_deployment_and_service)
are mocked, since this sandbox has no real target cluster to apply
anything to. What IS verified for real (not mocked): the isolated-client
construction logic (services/target_cluster.build_client_for_kubeconfig,
proven not to touch kubernetes-client's global default Configuration --
see the manual verification this was built against) and the vLLM
manifest rendering (tests/test_vllm_manifest.py, real Jinja2 + yaml.safe_load,
no mocking needed since it's pure templating).
"""
import asyncio
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "test-admin-password-123"


async def _reset():
    from sqlalchemy import delete
    from app.core.db import AsyncSessionLocal, init_db
    from app.models.user import User
    from app.models.ai_workload import AIWorkload
    from app.models.cluster import Cluster
    from app.services.auth import hash_password

    await init_db()
    async with AsyncSessionLocal() as session:
        await session.execute(delete(User))
        await session.execute(delete(AIWorkload))
        await session.execute(delete(Cluster))
        session.add(User(username=ADMIN_USERNAME, hashed_password=hash_password(ADMIN_PASSWORD)))
        await session.commit()


def _login(client) -> dict[str, str]:
    r = client.post("/api/v1/auth/login", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _create_cluster(client, headers, name="ai-target-cluster") -> str:
    r = client.post("/api/v1/clusters", json={"name": name, "control_plane_count": 1}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_create_workload_succeeds_when_target_cluster_reachable():
    asyncio.run(_reset())
    from fastapi.testclient import TestClient
    from app.main import app

    with patch("app.api.ai_workloads.target_cluster_service.get_client_for_cluster", return_value="fake-client"), \
         patch("app.api.ai_workloads.target_cluster_service.apply_deployment_and_service") as mock_apply:
        with TestClient(app) as client:
            headers = _login(client)
            cluster_id = _create_cluster(client, headers)

            r = client.post(
                "/api/v1/ai-workloads",
                json={
                    "name": "qwen-7b",
                    "cluster_id": cluster_id,
                    "model_id": "Qwen/Qwen2.5-7B-Instruct",
                    "gpu_count": 1,
                },
                headers=headers,
            )
            assert r.status_code == 201, r.text
            body = r.json()
            assert body["status"] == "running"
            assert body["service_endpoint"] == "http://qwen-7b.default.svc.cluster.local:8000/v1"
            assert body["error_message"] is None

            # confirm the actual manifests handed to apply_deployment_and_service
            # are real, correctly-shaped Deployment/Service objects, not
            # placeholders
            mock_apply.assert_called_once()
            _, deployment_manifest, service_manifest = mock_apply.call_args[0]
            assert deployment_manifest["kind"] == "Deployment"
            assert deployment_manifest["metadata"]["name"] == "qwen-7b"
            container = deployment_manifest["spec"]["template"]["spec"]["containers"][0]
            assert container["command"] == ["vllm", "serve", "Qwen/Qwen2.5-7B-Instruct"]
            assert container["resources"]["limits"]["nvidia.com/gpu"] == "1"
            assert service_manifest["kind"] == "Service"


def test_create_workload_records_failure_when_target_cluster_not_ready():
    """The single most common real failure mode: someone creates an AI
    workload for a cluster whose control plane hasn't finished coming up
    yet, so the <cluster-name>-kubeconfig Secret doesn't exist. This must
    not 500 -- it should record a clear, retryable failure."""
    asyncio.run(_reset())
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services.target_cluster import TargetClusterUnreachable

    with patch(
        "app.api.ai_workloads.target_cluster_service.get_client_for_cluster",
        side_effect=TargetClusterUnreachable("Secret metal3/ai-target-cluster-kubeconfig doesn't exist yet"),
    ):
        with TestClient(app) as client:
            headers = _login(client)
            cluster_id = _create_cluster(client, headers)

            r = client.post(
                "/api/v1/ai-workloads",
                json={"name": "not-ready-yet", "cluster_id": cluster_id, "model_id": "facebook/opt-125m"},
                headers=headers,
            )
            assert r.status_code == 201  # our own API call succeeded; the deploy attempt failed
            body = r.json()
            assert body["status"] == "failed"
            assert "doesn't exist yet" in body["error_message"]
            assert body["service_endpoint"] is None


def test_redeploy_retries_and_can_succeed_after_initial_failure():
    asyncio.run(_reset())
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services.target_cluster import TargetClusterUnreachable

    with patch(
        "app.api.ai_workloads.target_cluster_service.get_client_for_cluster",
        side_effect=TargetClusterUnreachable("not ready"),
    ):
        with TestClient(app) as client:
            headers = _login(client)
            cluster_id = _create_cluster(client, headers)
            create_resp = client.post(
                "/api/v1/ai-workloads",
                json={"name": "retry-me", "cluster_id": cluster_id, "model_id": "facebook/opt-125m"},
                headers=headers,
            )
            workload_id = create_resp.json()["id"]
            assert create_resp.json()["status"] == "failed"

    # cluster is "ready" now -- redeploy should succeed
    with patch("app.api.ai_workloads.target_cluster_service.get_client_for_cluster", return_value="fake-client"), \
         patch("app.api.ai_workloads.target_cluster_service.apply_deployment_and_service"):
        with TestClient(app) as client:
            headers = _login(client)
            r = client.post(f"/api/v1/ai-workloads/{workload_id}/redeploy", headers=headers)
            assert r.status_code == 200
            assert r.json()["status"] == "running"
            assert r.json()["error_message"] is None


def test_duplicate_workload_name_rejected():
    asyncio.run(_reset())
    from fastapi.testclient import TestClient
    from app.main import app

    with patch("app.api.ai_workloads.target_cluster_service.get_client_for_cluster", return_value="fake-client"), \
         patch("app.api.ai_workloads.target_cluster_service.apply_deployment_and_service"):
        with TestClient(app) as client:
            headers = _login(client)
            cluster_id = _create_cluster(client, headers)
            payload = {"name": "dup-workload", "cluster_id": cluster_id, "model_id": "facebook/opt-125m"}
            client.post("/api/v1/ai-workloads", json=payload, headers=headers)
            r = client.post("/api/v1/ai-workloads", json=payload, headers=headers)
            assert r.status_code == 409


def test_delete_workload_cleans_up_target_cluster_when_running():
    asyncio.run(_reset())
    from fastapi.testclient import TestClient
    from app.main import app

    with patch("app.api.ai_workloads.target_cluster_service.get_client_for_cluster", return_value="fake-client"), \
         patch("app.api.ai_workloads.target_cluster_service.apply_deployment_and_service"), \
         patch("app.api.ai_workloads.target_cluster_service.delete_deployment_and_service") as mock_delete:
        with TestClient(app) as client:
            headers = _login(client)
            cluster_id = _create_cluster(client, headers)
            create_resp = client.post(
                "/api/v1/ai-workloads",
                json={"name": "to-delete", "cluster_id": cluster_id, "model_id": "facebook/opt-125m"},
                headers=headers,
            )
            workload_id = create_resp.json()["id"]

            r = client.delete(f"/api/v1/ai-workloads/{workload_id}", headers=headers)
            assert r.status_code == 204
            mock_delete.assert_called_once()

            listing = client.get("/api/v1/ai-workloads", headers=headers).json()
            assert workload_id not in [w["id"] for w in listing]


def test_list_filters_by_cluster():
    asyncio.run(_reset())
    from fastapi.testclient import TestClient
    from app.main import app

    with patch("app.api.ai_workloads.target_cluster_service.get_client_for_cluster", return_value="fake-client"), \
         patch("app.api.ai_workloads.target_cluster_service.apply_deployment_and_service"):
        with TestClient(app) as client:
            headers = _login(client)
            cluster_a = _create_cluster(client, headers, "cluster-a")
            cluster_b = _create_cluster(client, headers, "cluster-b")
            client.post(
                "/api/v1/ai-workloads",
                json={"name": "on-a", "cluster_id": cluster_a, "model_id": "facebook/opt-125m"},
                headers=headers,
            )
            client.post(
                "/api/v1/ai-workloads",
                json={"name": "on-b", "cluster_id": cluster_b, "model_id": "facebook/opt-125m"},
                headers=headers,
            )

            only_a = client.get(f"/api/v1/ai-workloads?cluster_id={cluster_a}", headers=headers).json()
            assert [w["name"] for w in only_a] == ["on-a"]
