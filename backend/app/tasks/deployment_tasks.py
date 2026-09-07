"""
Celery task(s) that drive a Deployment through its phases:

  1. generate bmh.yaml / k8s-config.yaml / eph-net.yaml from the cluster spec
  2. bootstrap the ephemeral (PXE, in-memory) node as the temporary CAPI
     management cluster
  3. apply BareMetalHost objects, wait for them to become "available"
  4. apply Cluster / Metal3Cluster / KubeadmControlPlane / MachineDeployment
  5. wait for the control plane to come up, install addons
  6. (optional, opt-in via cluster_spec["pivot_to_self_hosting"]) pivot
     CAPI management from the ephemeral node to the newly-created target
     cluster via services/pivot.py -- decommissioning the ephemeral node
     itself is left as a site-specific extension point (see that
     module's docstring for why)

Each step publishes progress via ConnectionManager so the API layer's
WebSocket route can relay it to clients. Long-running waits are simple
polling loops here; swap in Metal3/CAPI event watches for lower latency
if needed.
"""
from __future__ import annotations

import asyncio
import logging
import tempfile
import time
import uuid
from pathlib import Path

from celery import Celery

from app.core.config import get_settings
from app.core.db import AsyncSessionLocal
from app.models.deployment import Deployment, DeploymentPhase
from app.services.addons import AddonInstallError, install_addon
from app.services.capi import CAPIService
from app.services.metal3 import Metal3Service
from app.services.pivot import pivot_management_to_target
from app.services.target_cluster import fetch_target_cluster_kubeconfig
from app.websocket.manager import manager

logger = logging.getLogger(__name__)
settings = get_settings()

celery_app = Celery(
    "metal3_deploy",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

_worker_loop: asyncio.AbstractEventLoop | None = None


def _get_worker_loop() -> asyncio.AbstractEventLoop:
    """Celery's prefork workers reuse the same process -- and therefore
    the same module-level `engine`/`AsyncSessionLocal` from app.core.db,
    and every asyncpg connection that engine's pool is holding onto --
    across every deployment task that process ever runs, for the rest of
    its life. asyncpg connections are bound to the event loop that
    created them; `asyncio.run()` tears its loop down the moment the
    coroutine it wraps returns. Calling `run_deployment_task` a second
    time in the same worker process used to call `asyncio.run()` again,
    handing the (still-pooled) connections from the first run's now-closed
    loop to a brand new one -- asyncpg then raises exactly
    "Future ... attached to a different loop" the moment anything tries
    to actually use one of those stale connections. This wasn't a
    hypothetical: it's what a real second deployment in the same worker
    process hit in production.

    Keeping one event loop alive for this worker process's entire life
    -- the same way the FastAPI app naturally has exactly one loop for
    its whole life under uvicorn -- avoids the mismatch entirely: every
    pooled connection this process ever opens stays bound to the one
    loop that's still running when it's reused.
    """
    global _worker_loop
    if _worker_loop is None or _worker_loop.is_closed():
        _worker_loop = asyncio.new_event_loop()
    return _worker_loop


async def _set_phase(deployment_id: str, phase: DeploymentPhase, message: str = "") -> None:
    async with AsyncSessionLocal() as session:
        # deployment_id arrives as a plain str -- Celery task args have to
        # be JSON-serializable, and uuid.UUID isn't, so api/deployments.py
        # passes str(deployment.id). But the Deployment.id column is a real
        # UUID type, and its bind processor (at least under SQLite, and
        # potentially asyncpg too) expects an actual uuid.UUID instance --
        # handing it a str blew up with "'str' object has no attribute
        # 'hex'" on the very first phase update of every deployment, before
        # this was ever exercised end to end.
        dep = await session.get(Deployment, uuid.UUID(deployment_id))
        if dep is None:
            return
        dep.phase = phase
        if message:
            dep.log = (dep.log or "") + f"\n[{phase.value}] {message}"
        await session.commit()
    await manager.broadcast(deployment_id, {"phase": phase.value, "message": message})


async def _run_deployment(deployment_id: str, cluster_spec: dict, namespace: str) -> None:
    metal3 = Metal3Service()
    capi = CAPIService()

    try:
        await _set_phase(deployment_id, DeploymentPhase.GENERATING_MANIFESTS, "rendering manifests")
        # manifests are rendered lazily inside apply_cluster(); here we just
        # validate the spec is renderable up-front and fail fast if not.
        capi.render_manifests(cluster_spec)

        await _set_phase(
            deployment_id, DeploymentPhase.BOOTSTRAPPING_EPHEMERAL_NODE,
            "waiting for ephemeral management cluster to be reachable",
        )
        # NOTE: bootstrapping the ephemeral node itself (PXE boot via the
        # site's own out-of-band/network-boot mechanism, kubeadm init,
        # installing Metal3+CAPI) is environment-specific and assumed to be
        # handled by existing tooling outside this project today;
        # this task assumes that has completed and MGMT_KUBECONFIG_PATH
        # points at the resulting single-node management cluster.

        await _set_phase(deployment_id, DeploymentPhase.APPLYING_BMH, "applying BareMetalHost objects")
        hosts = cluster_spec.get("hosts", [])
        # `hosts` comes from AssetPlannerService.generate_bundle -- one
        # entry per HardwareAsset actually assigned to this cluster's pools
        # (control-plane and worker alike). Those BMHs are expected to
        # already be registered via the /baremetalhosts API (which stores
        # BMC creds as Secrets); here we just confirm they exist and reach
        # "available" before moving on.

        await _set_phase(deployment_id, DeploymentPhase.WAITING_FOR_HOSTS, "polling BMH state")
        deadline = time.time() + settings.BMH_READY_TIMEOUT
        pending = {h["name"] for h in hosts}
        while pending and time.time() < deadline:
            for name in list(pending):
                status = metal3.get_host_status(name, namespace)
                state = (status or {}).get("provisioning", {}).get("state")
                if state in ("available", "provisioned", "ready"):
                    pending.discard(name)
            if pending:
                await asyncio.sleep(15)
        if pending:
            raise TimeoutError(f"BMH(s) not ready in time: {sorted(pending)}")

        await _set_phase(deployment_id, DeploymentPhase.APPLYING_CLUSTER, "applying Cluster API resources")
        capi.apply_cluster(cluster_spec, namespace)

        await _set_phase(
            deployment_id, DeploymentPhase.WAITING_FOR_CONTROL_PLANE,
            "waiting for KubeadmControlPlane to report Ready",
        )
        deadline = time.time() + settings.CLUSTER_PROVISION_TIMEOUT
        cluster_name = cluster_spec["name"]
        ready = False
        while time.time() < deadline:
            status = capi.get_cluster_status(cluster_name, namespace) or {}
            conditions = {c.get("type"): c.get("status") for c in status.get("conditions", [])}
            if conditions.get("ControlPlaneReady") == "True":
                ready = True
                break
            await asyncio.sleep(20)
        if not ready:
            raise TimeoutError("Control plane did not become ready in time")

        await _set_phase(deployment_id, DeploymentPhase.INSTALLING_ADDONS, "installing addon charts")
        requested_addons = cluster_spec.get("addons", [])
        addon_failures: list[str] = []
        if requested_addons:
            # Needs the target cluster's own kubeconfig, same convention
            # services/pivot.py and AI workload deployment already use --
            # by this point in the pipeline the control plane is up
            # (confirmed just above), so CAPI has already created the
            # "<cluster-name>-kubeconfig" Secret this reads.
            target_kubeconfig_yaml = fetch_target_cluster_kubeconfig(cluster_name, namespace)
            with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as kf:
                kf.write(target_kubeconfig_yaml)
                target_kubeconfig_path = kf.name
            try:
                for addon_name in requested_addons:
                    try:
                        output = install_addon(
                            addon_name,
                            kubeconfig_path=target_kubeconfig_path,
                            timeout_seconds=settings.ADDON_INSTALL_TIMEOUT,
                        )
                        await _set_phase(
                            deployment_id, DeploymentPhase.INSTALLING_ADDONS, f"[{addon_name}] installed\n{output}"
                        )
                    except AddonInstallError as exc:
                        # One broken addon shouldn't block the others --
                        # each is independent -- but must not be silently
                        # swallowed either: logged now, and surfaced as an
                        # overall deployment failure below once every
                        # addon has been attempted, so a partially-broken
                        # addon set is never reported as a quiet success.
                        addon_failures.append(addon_name)
                        await _set_phase(
                            deployment_id, DeploymentPhase.INSTALLING_ADDONS, f"[{addon_name}] FAILED\n{exc}"
                        )
            finally:
                Path(target_kubeconfig_path).unlink(missing_ok=True)

        if addon_failures:
            raise AddonInstallError(f"addon(s) failed to install: {', '.join(addon_failures)}")

        if cluster_spec.get("pivot_to_self_hosting"):
            await _set_phase(
                deployment_id, DeploymentPhase.PIVOTING_TO_TARGET_CLUSTER,
                "moving CAPI management from the ephemeral node to the new cluster itself",
            )
            # Only meaningful for the "ephemeral bootstrap node" pattern:
            # ephemeral_kubeconfig_path is that temporary management
            # cluster's own kubeconfig (MGMT_KUBECONFIG_PATH), not the
            # cluster this deployment just created. A permanent, already-
            # existing management cluster has no reason to pivot away
            # from managing what it just built, which is why this whole
            # block is opt-in (cluster_spec["pivot_to_self_hosting"]),
            # not automatic.
            target_kubeconfig_yaml = fetch_target_cluster_kubeconfig(cluster_name, namespace)
            pivot_log = pivot_management_to_target(
                source_kubeconfig_path=settings.MGMT_KUBECONFIG_PATH,
                target_kubeconfig_yaml=target_kubeconfig_yaml,
                namespace=namespace,
                timeout_seconds=settings.PIVOT_TIMEOUT,
            )
            await _set_phase(deployment_id, DeploymentPhase.PIVOTING_TO_TARGET_CLUSTER, pivot_log)
            # Decommissioning the ephemeral node itself (powering it off,
            # releasing it back to inventory, tearing down whatever
            # temporary compute it was -- a BareMetalHost being reused,
            # a VM, a container) is deliberately NOT done here: what an
            # "ephemeral node" concretely IS varies per deployment (see
            # deploy/bootstrap-management-cluster/README.md), and guessing
            # wrong risks tearing down something still in use. Left as an
            # extension point for a site-specific hook once pivoting is
            # confirmed successful, the same way addon installation above
            # is.

        await _set_phase(deployment_id, DeploymentPhase.COMPLETE, "deployment complete")

    except Exception as exc:  # noqa: BLE001
        logger.exception("Deployment %s failed", deployment_id)
        async with AsyncSessionLocal() as session:
            dep = await session.get(Deployment, uuid.UUID(deployment_id))
            if dep:
                dep.phase = DeploymentPhase.FAILED
                dep.error_message = str(exc)
                await session.commit()
        await manager.broadcast(deployment_id, {"phase": "failed", "message": str(exc)})
        raise


@celery_app.task(name="deployment.run")
def run_deployment_task(deployment_id: str, cluster_spec: dict, namespace: str) -> None:
    loop = _get_worker_loop()
    loop.run_until_complete(_run_deployment(deployment_id, cluster_spec, namespace))
