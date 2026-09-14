"""
The actual trigger behind "click enable in the App Store and it
installs itself" -- api/addons.py's enable_addon endpoint calls this
(via .delay(), same async pattern as deployment_tasks.py) whenever the
target cluster this addon.request is against is already deployed and
has a real kubeconfig to install anything onto. Before this existed,
enabling an addon only ever recorded intent in Cluster.spec["addons"]
-- the real install (services/addons.py) only ran during a cluster's
very first deployment (deployment_tasks.py's installing_addons phase),
never again afterward.

Uses the SAME persistent-worker-event-loop pattern deployment_tasks.py
already established (see that module's own _get_worker_loop docstring
for the real production bug this avoids -- asyncio.run() per task leaks
asyncpg connections bound to a now-closed loop across tasks in the same
Celery worker process) rather than reintroducing that bug in a second
task module.
"""
from __future__ import annotations

import asyncio
import logging
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from celery import Celery

from app.core.config import get_settings
from app.core.db import AsyncSessionLocal
from app.models.cluster import Cluster
from app.services.addons import AddonInstallError, install_addon
from app.services.target_cluster import fetch_target_cluster_kubeconfig

logger = logging.getLogger(__name__)
settings = get_settings()

celery_app = Celery(
    "metal3_deploy_addons",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

_worker_loop: asyncio.AbstractEventLoop | None = None


def _get_worker_loop() -> asyncio.AbstractEventLoop:
    global _worker_loop
    if _worker_loop is None or _worker_loop.is_closed():
        _worker_loop = asyncio.new_event_loop()
    return _worker_loop


async def _set_addon_status(cluster_id: str, addon_name: str, status: str, message: str = "") -> None:
    async with AsyncSessionLocal() as session:
        cluster = await session.get(Cluster, uuid.UUID(cluster_id))
        if cluster is None:
            logger.warning("cluster %s vanished before addon status could be recorded", cluster_id)
            return
        current = dict(cluster.addon_status)
        current[addon_name] = {
            "status": status,
            "message": message,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        cluster.addon_status = current
        await session.commit()


async def _install_addon(cluster_id: str, addon_name: str) -> None:
    async with AsyncSessionLocal() as session:
        cluster = await session.get(Cluster, uuid.UUID(cluster_id))
        if cluster is None:
            raise RuntimeError(f"cluster {cluster_id} not found")
        cluster_name, namespace = cluster.name, cluster.namespace

    await _set_addon_status(cluster_id, addon_name, "installing")
    try:
        target_kubeconfig_yaml = fetch_target_cluster_kubeconfig(cluster_name, namespace)
    except Exception as exc:  # noqa: BLE001 -- surfaced as addon status, not a bare task failure
        await _set_addon_status(cluster_id, addon_name, "failed", f"could not fetch target kubeconfig: {exc}")
        return

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as kf:
        kf.write(target_kubeconfig_yaml)
        kubeconfig_path = kf.name
    try:
        output = install_addon(addon_name, kubeconfig_path=kubeconfig_path, timeout_seconds=settings.ADDON_INSTALL_TIMEOUT)
        await _set_addon_status(cluster_id, addon_name, "installed", output)
    except AddonInstallError as exc:
        await _set_addon_status(cluster_id, addon_name, "failed", str(exc))
    finally:
        Path(kubeconfig_path).unlink(missing_ok=True)


@celery_app.task(name="addon.install")
def install_addon_task(cluster_id: str, addon_name: str) -> None:
    loop = _get_worker_loop()
    loop.run_until_complete(_install_addon(cluster_id, addon_name))
