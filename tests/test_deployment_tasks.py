"""
Runs the real `_run_deployment` orchestration function against a real
(sqlite) database -- this never had any test coverage before, and it
turned out to be broken: every call to `_set_phase` crashed immediately
with `AttributeError: 'str' object has no attribute 'hex'`, because
`deployment_id` arrives as a plain str (Celery task args must be
JSON-serializable, so api/deployments.py passes str(deployment.id)) but
the Deployment.id column's UUID type needs an actual uuid.UUID instance
for its bind processor. That means no deployment, ever, could progress
past its very first phase update -- this test would have caught it.

Metal3Service/CAPIService are mocked (no real cluster available here);
everything else -- the DB writes, the phase state machine, the exception
handling -- runs for real.
"""
import asyncio
import os
import sys
import uuid
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")

from app.core.db import AsyncSessionLocal, init_db  # noqa: E402
from app.models.cluster import Cluster  # noqa: E402
from app.models.deployment import Deployment, DeploymentPhase  # noqa: E402
from app.tasks.deployment_tasks import _run_deployment  # noqa: E402


async def _make_cluster_and_deployment(name: str) -> tuple[uuid.UUID, uuid.UUID]:
    await init_db()
    async with AsyncSessionLocal() as session:
        cluster = Cluster(name=name, control_plane_count=1, control_plane_endpoint="10.0.0.1")
        session.add(cluster)
        await session.commit()
        await session.refresh(cluster)

        deployment = Deployment(cluster_id=cluster.id)
        session.add(deployment)
        await session.commit()
        await session.refresh(deployment)
        return cluster.id, deployment.id


async def _get_deployment(deployment_id: uuid.UUID) -> Deployment:
    async with AsyncSessionLocal() as session:
        dep = await session.get(Deployment, deployment_id)
        assert dep is not None
        return dep


MINIMAL_CLUSTER_SPEC = {
    "name": "deploy-task-test-cluster",
    "namespace": "metal3",
    "control_plane_count": 1,
    "control_plane_endpoint": "10.0.0.1",
    "worker_pools": [],
    "hosts": [{"name": "cp-01"}],
}


def test_full_deployment_reaches_complete():
    _, deployment_id = asyncio.run(_make_cluster_and_deployment("deploy-task-test-cluster"))

    with patch("app.tasks.deployment_tasks.CAPIService.render_manifests", return_value=[]), \
         patch("app.tasks.deployment_tasks.CAPIService.apply_cluster", return_value=[]), \
         patch(
             "app.tasks.deployment_tasks.Metal3Service.get_host_status",
             return_value={"provisioning": {"state": "available"}},
         ), \
         patch(
             "app.tasks.deployment_tasks.CAPIService.get_cluster_status",
             return_value={"conditions": [{"type": "ControlPlaneReady", "status": "True"}]},
         ):
        asyncio.run(_run_deployment(str(deployment_id), MINIMAL_CLUSTER_SPEC, "metal3"))

    dep = asyncio.run(_get_deployment(deployment_id))
    assert dep.phase == DeploymentPhase.COMPLETE
    assert dep.error_message is None
    # every phase should have left a trace in the log, in order
    for phase in ("generating_manifests", "applying_bmh", "waiting_for_hosts", "applying_cluster"):
        assert f"[{phase}]" in dep.log


def test_deployment_records_failure_without_crashing_the_handler_itself():
    """This exercises the except-block's own DB write -- which used the
    exact same broken str-vs-UUID lookup and would previously have thrown
    a *second*, unrelated exception while trying to record the first one."""
    _, deployment_id = asyncio.run(_make_cluster_and_deployment("deploy-task-test-cluster-fail"))

    with patch(
        "app.tasks.deployment_tasks.CAPIService.render_manifests",
        side_effect=ValueError("cluster_spec is missing something the template needs"),
    ):
        try:
            asyncio.run(_run_deployment(str(deployment_id), MINIMAL_CLUSTER_SPEC, "metal3"))
        except ValueError:
            pass  # _run_deployment re-raises after recording the failure -- expected

    dep = asyncio.run(_get_deployment(deployment_id))
    assert dep.phase == DeploymentPhase.FAILED
    assert "cluster_spec is missing something" in dep.error_message
