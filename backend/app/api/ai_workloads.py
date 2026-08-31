"""
Deploys/manages vLLM inference workloads on TARGET clusters (ones this
project already provisioned) -- a fundamentally different operation from
every other router in this project, which only ever touch the
MANAGEMENT cluster. See services/target_cluster.py's module docstring
for why that needed a new, isolated-per-cluster client mechanism rather
than reusing services/kubernetes.py's KubernetesService.

Exposing a workload outside its target cluster (a real DNS name/TLS
cert reachable from the internet) is deliberately NOT handled here --
that's the same problem the apigateway/bgp-lb addons already solve
generically for any service on a cluster (see services/addon_catalog.py),
not something to reinvent per-workload.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.ai_workload import AIWorkload, AIWorkloadStatus
from app.models.cluster import Cluster
from app.schemas.ai_workload import AIWorkloadCreate, AIWorkloadRead
from app.services import target_cluster as target_cluster_service
from app.services.target_cluster import TargetClusterUnreachable
from app.services.yaml_generator import YamlGeneratorService

router = APIRouter(prefix="/ai-workloads", tags=["ai-workloads"])
yaml_gen = YamlGeneratorService()


def _service_endpoint(workload: AIWorkload) -> str:
    return f"http://{workload.name}.{workload.namespace}.svc.cluster.local:8000/v1"


async def _deploy_to_target_cluster(workload: AIWorkload, cluster: Cluster, db: AsyncSession) -> None:
    """Renders the vLLM manifests and applies them to the target cluster,
    updating the workload's status/error_message either way. Split out
    from create_workload so redeploy_workload can reuse it without
    duplicating the render/apply/status-update sequence."""
    workload_spec = {
        "name": workload.name,
        "namespace": workload.namespace,
        "model_id": workload.model_id,
        "gpu_count": workload.gpu_count,
        "replicas": workload.replicas,
    }
    yaml_out = yaml_gen.render_vllm_deployment(workload_spec)
    deployment_manifest, service_manifest = yaml_gen.parse_multi(yaml_out)

    try:
        target_client = target_cluster_service.get_client_for_cluster(cluster.name, cluster.namespace)
        target_cluster_service.apply_deployment_and_service(target_client, deployment_manifest, service_manifest)
    except TargetClusterUnreachable as exc:
        workload.status = AIWorkloadStatus.FAILED
        workload.error_message = str(exc)
        await db.commit()
        return
    except Exception as exc:  # noqa: BLE001
        workload.status = AIWorkloadStatus.FAILED
        workload.error_message = f"Failed to apply to target cluster: {exc}"
        await db.commit()
        return

    workload.status = AIWorkloadStatus.RUNNING
    workload.error_message = None
    workload.service_endpoint = _service_endpoint(workload)
    await db.commit()


@router.get("", response_model=list[AIWorkloadRead])
async def list_workloads(cluster_id: uuid.UUID | None = None, db: AsyncSession = Depends(get_db)):
    query = select(AIWorkload).order_by(AIWorkload.name)
    if cluster_id:
        query = query.where(AIWorkload.cluster_id == cluster_id)
    result = await db.scalars(query)
    return result.all()


@router.post("", response_model=AIWorkloadRead, status_code=201)
async def create_workload(payload: AIWorkloadCreate, db: AsyncSession = Depends(get_db)):
    cluster = await db.get(Cluster, payload.cluster_id)
    if not cluster:
        raise HTTPException(404, "Cluster not found")

    existing = await db.scalar(select(AIWorkload).where(AIWorkload.name == payload.name))
    if existing:
        raise HTTPException(409, f"A workload named '{payload.name}' already exists")

    workload = AIWorkload(
        name=payload.name,
        cluster_id=payload.cluster_id,
        namespace=payload.namespace,
        model_id=payload.model_id,
        gpu_count=payload.gpu_count,
        replicas=payload.replicas,
        status=AIWorkloadStatus.PENDING,
    )
    db.add(workload)
    await db.commit()
    await db.refresh(workload)

    workload.status = AIWorkloadStatus.DEPLOYING
    await db.commit()
    await _deploy_to_target_cluster(workload, cluster, db)
    await db.refresh(workload)
    return workload


@router.post("/{workload_id}/redeploy", response_model=AIWorkloadRead)
async def redeploy_workload(workload_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Retries applying to the target cluster -- for when the first
    attempt failed because the cluster's kubeconfig Secret didn't exist
    yet (control plane still provisioning), the most common failure mode
    for a workload created right after triggering a cluster deployment."""
    workload = await db.get(AIWorkload, workload_id)
    if not workload:
        raise HTTPException(404, "Workload not found")
    cluster = await db.get(Cluster, workload.cluster_id)
    if not cluster:
        raise HTTPException(404, "Cluster not found")

    workload.status = AIWorkloadStatus.DEPLOYING
    await db.commit()
    await _deploy_to_target_cluster(workload, cluster, db)
    await db.refresh(workload)
    return workload


@router.delete("/{workload_id}", status_code=204)
async def delete_workload(workload_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    workload = await db.get(AIWorkload, workload_id)
    if not workload:
        raise HTTPException(404, "Workload not found")
    cluster = await db.get(Cluster, workload.cluster_id)

    if cluster and workload.status == AIWorkloadStatus.RUNNING:
        try:
            target_client = target_cluster_service.get_client_for_cluster(cluster.name, cluster.namespace)
            target_cluster_service.delete_deployment_and_service(target_client, workload.namespace, workload.name)
        except TargetClusterUnreachable:
            # Cluster's gone or never finished provisioning -- nothing
            # left to clean up there either way; still remove our own
            # record rather than leaving an orphaned row no UI action
            # can ever clear.
            pass

    await db.delete(workload)
    await db.commit()
