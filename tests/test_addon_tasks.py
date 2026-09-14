"""
Covers tasks/addon_tasks.py -- the actual trigger behind "click enable
in the App Store and it installs itself right now" (api/addons.py's
enable_addon calls install_addon_task.delay(...), see
tests/test_addons.py for the HTTP-layer side of that, mocked there
since it needs no real Celery broker to verify enable_addon's own
behavior). This file covers the task body itself: does it really fetch
the target kubeconfig, call the real installer, and record accurate
status -- including every real failure mode a click could hit.
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
from app.services.addons import AddonInstallError  # noqa: E402
from app.tasks.addon_tasks import install_addon_task, _install_addon  # noqa: E402


async def _make_cluster(name: str) -> uuid.UUID:
    await init_db()
    async with AsyncSessionLocal() as session:
        cluster = Cluster(name=name, control_plane_count=1, control_plane_endpoint="10.0.0.1")
        session.add(cluster)
        await session.commit()
        await session.refresh(cluster)
        return cluster.id


async def _get_cluster(cluster_id: uuid.UUID) -> Cluster:
    async with AsyncSessionLocal() as session:
        return await session.get(Cluster, cluster_id)


def test_successful_install_records_installed_status_with_real_output():
    cluster_id = asyncio.run(_make_cluster("addon-task-success-test"))

    with patch(
        "app.tasks.addon_tasks.fetch_target_cluster_kubeconfig", return_value="apiVersion: v1\nkind: Config"
    ) as mock_fetch, patch(
        "app.tasks.addon_tasks.install_addon", return_value="kubevirt installed ok"
    ) as mock_install:
        asyncio.run(_install_addon(str(cluster_id), "kubevirt"))

    mock_fetch.assert_called_once_with("addon-task-success-test", "metal3")
    mock_install.assert_called_once()
    assert mock_install.call_args.args[0] == "kubevirt"

    cluster = asyncio.run(_get_cluster(cluster_id))
    assert cluster.addon_status["kubevirt"]["status"] == "installed"
    assert cluster.addon_status["kubevirt"]["message"] == "kubevirt installed ok"
    assert "updated_at" in cluster.addon_status["kubevirt"]


def test_missing_target_kubeconfig_records_a_clear_failed_status_not_a_bare_crash():
    """The most common real-world case a click will hit: the cluster
    exists but has never been deployed (or is still provisioning), so
    there's no "<name>-kubeconfig" Secret yet. Must record WHY, not
    crash the Celery task with an unhandled exception."""
    cluster_id = asyncio.run(_make_cluster("addon-task-no-kubeconfig-test"))

    with patch(
        "app.tasks.addon_tasks.fetch_target_cluster_kubeconfig",
        side_effect=RuntimeError("Secret 'addon-task-no-kubeconfig-test-kubeconfig' not found"),
    ):
        asyncio.run(_install_addon(str(cluster_id), "kubevirt"))  # must not raise

    cluster = asyncio.run(_get_cluster(cluster_id))
    assert cluster.addon_status["kubevirt"]["status"] == "failed"
    assert "not found" in cluster.addon_status["kubevirt"]["message"]


def test_install_failure_records_the_real_addon_install_error_message():
    cluster_id = asyncio.run(_make_cluster("addon-task-install-fail-test"))

    with patch(
        "app.tasks.addon_tasks.fetch_target_cluster_kubeconfig", return_value="apiVersion: v1\nkind: Config"
    ), patch(
        "app.tasks.addon_tasks.install_addon",
        side_effect=AddonInstallError("helm upgrade --install failed: connection refused"),
    ):
        asyncio.run(_install_addon(str(cluster_id), "kube-ovn"))  # must not raise

    cluster = asyncio.run(_get_cluster(cluster_id))
    assert cluster.addon_status["kube-ovn"]["status"] == "failed"
    assert "connection refused" in cluster.addon_status["kube-ovn"]["message"]


def test_status_transitions_through_installing_before_landing_on_a_final_state():
    """Confirms the "installing" intermediate status actually gets
    written (not skipped straight to the final state), since that's
    what the frontend would poll to show a live "installing..."
    indicator rather than nothing happening until it's done."""
    cluster_id = asyncio.run(_make_cluster("addon-task-installing-state-test"))
    seen_statuses = []

    real_set_status = None
    import app.tasks.addon_tasks as addon_tasks_module
    real_set_status = addon_tasks_module._set_addon_status

    async def spy_set_status(cid, name, status, message=""):
        seen_statuses.append(status)
        await real_set_status(cid, name, status, message)

    with patch("app.tasks.addon_tasks._set_addon_status", side_effect=spy_set_status), \
         patch("app.tasks.addon_tasks.fetch_target_cluster_kubeconfig", return_value="apiVersion: v1\nkind: Config"), \
         patch("app.tasks.addon_tasks.install_addon", return_value="ok"):
        asyncio.run(_install_addon(str(cluster_id), "kubevirt"))

    assert seen_statuses == ["installing", "installed"]


def test_multiple_addons_on_the_same_cluster_do_not_clobber_each_others_status():
    cluster_id = asyncio.run(_make_cluster("addon-task-multi-addon-test"))

    with patch("app.tasks.addon_tasks.fetch_target_cluster_kubeconfig", return_value="apiVersion: v1\nkind: Config"), \
         patch("app.tasks.addon_tasks.install_addon", side_effect=["kubevirt ok", AddonInstallError("kube-ovn broke")]):
        asyncio.run(_install_addon(str(cluster_id), "kubevirt"))
        asyncio.run(_install_addon(str(cluster_id), "kube-ovn"))

    cluster = asyncio.run(_get_cluster(cluster_id))
    assert cluster.addon_status["kubevirt"]["status"] == "installed"
    assert cluster.addon_status["kube-ovn"]["status"] == "failed"


def test_celery_task_wrapper_reuses_the_persistent_worker_loop():
    """Same regression this project already fixed once for
    deployment_tasks.py (see that module's own _get_worker_loop
    docstring) -- must not reintroduce asyncio.run()-per-task here,
    which would leak asyncpg connections bound to a now-closed loop
    across tasks in the same Celery worker process."""
    import app.tasks.addon_tasks as addon_tasks_module

    addon_tasks_module._worker_loop = None
    cluster_id_1 = asyncio.run(_make_cluster("addon-task-loop-reuse-1"))
    cluster_id_2 = asyncio.run(_make_cluster("addon-task-loop-reuse-2"))

    with patch("app.tasks.addon_tasks.fetch_target_cluster_kubeconfig", return_value="apiVersion: v1\nkind: Config"), \
         patch("app.tasks.addon_tasks.install_addon", return_value="ok"):
        install_addon_task.run(str(cluster_id_1), "kubevirt")
        loop_after_first = addon_tasks_module._worker_loop
        assert loop_after_first is not None and not loop_after_first.is_closed()

        install_addon_task.run(str(cluster_id_2), "kubevirt")
        loop_after_second = addon_tasks_module._worker_loop

    assert loop_after_second is loop_after_first
