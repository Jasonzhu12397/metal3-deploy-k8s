"""
Celery task(s) that drive a Deployment through its phases:

  1. generate bmh.yaml / k8s-config.yaml / eph-net.yaml from the cluster spec
  2. bootstrap the ephemeral (PXE, in-memory) node as the temporary CAPI
     management cluster
  3. apply BareMetalHost objects, wait for them to become "available"
  4. apply Cluster / Metal3Cluster / KubeadmControlPlane / MachineDeployment
  5. wait for the control plane to come up, install addons
  6. (optionally) pivot CAPI management from the ephemeral node to the
     newly-created target cluster, then decommission the ephemeral node

Each step publishes progress via ConnectionManager so the API layer's
WebSocket route can relay it to clients. Long-running waits are simple
polling loops here; swap in Metal3/CAPI event watches for lower latency
if needed.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid

from celery import Celery

from app.core.config import get_settings
from app.core.db import AsyncSessionLocal
from app.models.deployment import Deployment, DeploymentPhase
from app.services.capi import CAPIService
from app.services.metal3 import Metal3Service
from app.websocket.manager import manager

logger = logging.getLogger(__name__)
settings = get_settings()

celery_app = Celery(
    "metal3_deploy",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)


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
        # NOTE: bootstrapping the ephemeral node itself (PXE boot via SDI3 /
        # netconf, kubeadm init, installing Metal3+CAPI) is environment
        # specific and orchestrated by ccdadm/`cluster bootstrap` today;
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
        # Addon install (calico, ceph, ecfe, apigateway, pm, dex, ...) is
        # deliberately left as an extension point -- wire in Helm/kubectl
        # apply calls here driven by cluster_spec["addons"].

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
    asyncio.run(_run_deployment(deployment_id, cluster_spec, namespace))
