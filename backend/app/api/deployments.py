from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import decode_token_for_websocket
from app.models.cluster import Cluster, InfrastructureProvider
from app.models.deployment import Deployment
from app.models.hardware_asset import HardwareAsset
from app.models.pool_assignment import NodePoolAssignment
from app.schemas.deployment import DeploymentCreate, DeploymentRead
from app.services.asset_planner import AssetPlannerService
from app.services.cloud_planner import CloudPlannerService
from app.tasks.deployment_tasks import run_deployment_task
from app.websocket.manager import manager

router = APIRouter(prefix="/deployments", tags=["deployments"])
# Separate router for the WebSocket route: it's included in main.py WITHOUT
# the HTTP-only bearer-token dependency (HTTPBearer reads an Authorization
# header, which browsers cannot set on a WebSocket handshake) and instead
# checks a `?token=` query param by hand below.
ws_router = APIRouter(prefix="/deployments", tags=["deployments"])
planner = AssetPlannerService()
cloud_planner = CloudPlannerService()


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

    if cluster.infrastructure_provider != InfrastructureProvider.METAL3:
        # No physical hardware involved for a cloud/VM provider -- the
        # cluster's own worker_pools + flavor/image config (set at
        # creation time) is the whole story, and there's nothing to wait
        # on before "applying_cluster" (no BMH, no Ironic inspection).
        cluster_spec = cloud_planner.build_cluster_spec(cluster)
    else:
        # Derive what to deploy from the *actual* hardware assignments
        # (NodePoolAssignment), not the static worker_pools a cluster may
        # have been created with. Those two used to be independent -- a
        # cluster created with worker_pools=[] and then given hardware
        # entirely through POST /pools/{pool}/assign would deploy nothing,
        # or deploy stale config left over from creation time. This is
        # also where control-plane vs. worker role gets resolved (see
        # AssetPlannerService.generate_bundle), which is required for a
        # single-control-plane-node deployment to work at all: without
        # it, KubeadmControlPlane.replicas stays at whatever the cluster
        # was created with instead of matching the one node that was
        # actually assigned.
        result = await db.scalars(
            select(NodePoolAssignment).where(NodePoolAssignment.cluster_id == cluster.id)
        )
        assignments = result.all()
        if not assignments:
            raise HTTPException(
                409,
                "No hardware assigned to any pool yet -- call /clusters/{id}/pools/{pool}/assign first",
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
        # Keep the cluster row's control_plane_count truthful once we
        # actually deploy -- it may have been overridden by how much
        # control-plane hardware ended up assigned (e.g. a single-node
        # cluster created with the default of 3, then given exactly one
        # control-plane asset). Cloud providers don't have this
        # discrepancy -- their control_plane_count is authoritative from
        # creation time since there's no hardware assignment step to
        # override it.
        cluster.control_plane_count = cluster_spec["control_plane_count"]

    deployment = Deployment(cluster_id=cluster.id)
    db.add(deployment)
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


@ws_router.websocket("/{deployment_id}/ws")
async def deployment_progress_ws(websocket: WebSocket, deployment_id: str, token: str | None = None):
    # Browsers can't set an Authorization header on a WebSocket handshake,
    # so the token travels as a query param here instead (?token=...) and
    # is checked manually against this router, which main.py includes
    # without the HTTP bearer dependency the rest of /deployments gets.
    subject = decode_token_for_websocket(token)
    if subject is None:
        await websocket.close(code=4401)
        return

    await manager.connect(deployment_id, websocket)
    try:
        while True:
            # Client doesn't need to send anything; this just keeps the
            # connection open so we can push broadcast() events to it.
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(deployment_id, websocket)
