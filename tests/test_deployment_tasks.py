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


def test_run_deployment_task_reuses_one_event_loop_across_calls():
    """The actual bug this covers: Celery's prefork workers reuse the
    same process -- and the same module-level engine/AsyncSessionLocal,
    and every asyncpg connection its pool is holding onto -- across every
    task that process ever runs. `run_deployment_task` used to call
    `asyncio.run(...)`, which tears its event loop down the moment the
    coroutine returns; asyncpg connections are bound to the loop that
    created them, so a second deployment in the same worker process
    handed pooled connections from the first (now-closed) loop to a
    brand new one, and asyncpg raised "Future ... attached to a
    different loop" the moment anything tried to reuse one -- this
    happened for real, not hypothetically.

    Can't reproduce the exact asyncpg failure under this project's
    sqlite-backed test suite (aiosqlite doesn't bind connections to a
    specific loop the same way), so this test verifies the actual fix
    mechanism instead: run_deployment_task's underlying event loop is
    the SAME object across two sequential calls, not a fresh one each
    time -- confirming the fix is real, not just "happens not to crash
    under sqlite regardless of the underlying loop-per-call bug."
    """
    import app.tasks.deployment_tasks as deployment_tasks_module
    from app.tasks.deployment_tasks import run_deployment_task

    deployment_tasks_module._worker_loop = None  # simulate a fresh worker process

    _, dep_id_1 = asyncio.run(_make_cluster_and_deployment("loop-reuse-test-1"))
    _, dep_id_2 = asyncio.run(_make_cluster_and_deployment("loop-reuse-test-2"))

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
        run_deployment_task.run(str(dep_id_1), MINIMAL_CLUSTER_SPEC, "metal3")
        loop_after_first_call = deployment_tasks_module._worker_loop
        assert loop_after_first_call is not None
        assert not loop_after_first_call.is_closed(), (
            "the worker's event loop must stay open between tasks -- a closed loop here "
            "means we're back to the asyncio.run()-per-call bug this test exists to catch"
        )

        run_deployment_task.run(str(dep_id_2), MINIMAL_CLUSTER_SPEC, "metal3")
        loop_after_second_call = deployment_tasks_module._worker_loop

    assert loop_after_second_call is loop_after_first_call, (
        "run_deployment_task must reuse the SAME event loop across calls in the same "
        "worker process, not create a fresh one per task -- otherwise pooled asyncpg "
        "connections from the first task's loop get handed to the second task's "
        "different loop and asyncpg raises 'attached to a different loop'"
    )

    dep1 = asyncio.run(_get_deployment(dep_id_1))
    dep2 = asyncio.run(_get_deployment(dep_id_2))
    assert dep1.phase == DeploymentPhase.COMPLETE
    assert dep2.phase == DeploymentPhase.COMPLETE
