from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.cluster import Cluster
from app.models.deployment import Deployment
from app.models.hardware_asset import HardwareAsset
from app.models.pool_assignment import NodePoolAssignment
from app.schemas.deployment import DeploymentCreate, DeploymentRead
from app.services.asset_planner import AssetPlannerService
from app.tasks.deployment_tasks import run_deployment_task
from app.websocket.manager import manager

router = APIRouter(prefix="/deployments", tags=["deployments"])
planner = AssetPlannerService()


@router.get("", response_model=list[DeploymentRead])
async def list_deployments(cluster_id: uuid.UUID | None = None, db: AsyncSession = Depends(get_db)):
    query = select(Deployment).order_by(Deployment.created_at.desc())
    if cluster_id:
        query = query.where(Deployment.cluster_id == cluster_id)
    result = await db.scalars(query)
    return result.all()


@router.post("", response_model=DeploymentRead, status_code=201)
async def start_deployment(payload: DeploymentCreate, db: AsyncSession = Depends(get_db)):
    cluster = await db.get(Cluster, payload.cluster_id)
    if not cluster:
        raise HTTPException(404, "Cluster not found")

    # Derive what to deploy from the *actual* hardware assignments
    # (NodePoolAssignment), not the static worker_pools a cluster may have
    # been created with. Those two used to be independent -- a cluster
    # created with worker_pools=[] and then given hardware entirely through
    # POST /pools/{pool}/assign would deploy nothing, or deploy stale config
    # left over from creation time. This is also where control-plane vs.
    # worker role gets resolved (see AssetPlannerService.generate_bundle),
    # which is required for a single-control-plane-node deployment to work
    # at all: without it, KubeadmControlPlane.replicas stays at whatever
    # the cluster was created with instead of matching the one node that
    # was actually assigned.
    result = await db.scalars(
        select(NodePoolAssignment).where(NodePoolAssignment.cluster_id == cluster.id)
    )
    assignments = result.all()
    if not assignments:
        raise HTTPException(
            409, "No hardware assigned to any pool yet -- call /clusters/{id}/pools/{pool}/assign first"
        )

    pools: dict[str, tuple[list[HardwareAsset], list[NodePoolAssignment]]] = {}
    for assignment in assignments:
        asset = await db.get(HardwareAsset, assignment.asset_id)
        if not asset:
            continue
        pools.setdefault(assignment.pool_name, ([], []))
        pools[assignment.pool_name][0].append(asset)
        pools[assignment.pool_name][1].append(assignment)

    base_cluster_spec = {
        "name": cluster.name,
        "namespace": cluster.namespace,
        "control_plane_count": cluster.control_plane_count,
        "control_plane_endpoint": cluster.control_plane_endpoint,
        **cluster.spec,
    }

    try:
        bundle = planner.generate_bundle(base_cluster_spec, pools)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    cluster_spec = bundle["cluster_spec"]

    deployment = Deployment(cluster_id=cluster.id)
    db.add(deployment)
    # Keep the cluster row's control_plane_count truthful once we actually
    # deploy -- it may have been overridden by how much control-plane
    # hardware ended up assigned (e.g. a single-node cluster created with
    # the default of 3, then given exactly one control-plane asset).
    cluster.control_plane_count = cluster_spec["control_plane_count"]
    await db.commit()
    await db.refresh(deployment)

    async_result = run_deployment_task.delay(str(deployment.id), cluster_spec, cluster.namespace)
    deployment.celery_task_id = async_result.id
    await db.commit()
    await db.refresh(deployment)
    return deployment


@router.get("/{deployment_id}", response_model=DeploymentRead)
async def get_deployment(deployment_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    deployment = await db.get(Deployment, deployment_id)
    if not deployment:
        raise HTTPException(404, "Deployment not found")
    return deployment


@router.websocket("/{deployment_id}/ws")
async def deployment_progress_ws(websocket: WebSocket, deployment_id: str):
    await manager.connect(deployment_id, websocket)
    try:
        while True:
            # Client doesn't need to send anything; this just keeps the
            # connection open so we can push broadcast() events to it.
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(deployment_id, websocket)
