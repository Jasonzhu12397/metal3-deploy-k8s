from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.cluster import Cluster
from app.models.deployment import Deployment, DeploymentPhase
from app.models.hardware_asset import AssetStatus, HardwareAsset
from app.models.machine import Machine
from app.models.pool_assignment import NodePoolAssignment
from app.schemas.cluster import ClusterCreate, ClusterRead, ClusterUpdate

router = APIRouter(prefix="/clusters", tags=["clusters"])

_TERMINAL_PHASES = {DeploymentPhase.COMPLETE, DeploymentPhase.FAILED}


@router.post("", response_model=ClusterRead, status_code=201)
async def create_cluster(payload: ClusterCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.scalar(select(Cluster).where(Cluster.name == payload.name))
    if existing:
        raise HTTPException(409, f"Cluster '{payload.name}' already exists")

    spec = dict(payload.spec)
    if payload.control_plane_flavor:
        spec["control_plane_flavor"] = payload.control_plane_flavor
    if payload.control_plane_image:
        spec["control_plane_image"] = payload.control_plane_image

    cluster = Cluster(
        name=payload.name,
        namespace=payload.namespace,
        infrastructure_provider=payload.infrastructure_provider,
        control_plane_count=payload.control_plane_count,
        control_plane_endpoint=payload.control_plane_endpoint,
        worker_pool_config={"pools": [p.model_dump() for p in payload.worker_pools]},
        spec=spec,
    )
    db.add(cluster)
    await db.commit()
    await db.refresh(cluster)
    return cluster


@router.get("", response_model=list[ClusterRead])
async def list_clusters(db: AsyncSession = Depends(get_db)):
    result = await db.scalars(select(Cluster).order_by(Cluster.created_at.desc()))
    return result.all()


@router.get("/{cluster_id}", response_model=ClusterRead)
async def get_cluster(cluster_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    cluster = await db.get(Cluster, cluster_id)
    if not cluster:
        raise HTTPException(404, "Cluster not found")
    return cluster


@router.patch("/{cluster_id}", response_model=ClusterRead)
async def update_cluster(
    cluster_id: uuid.UUID, payload: ClusterUpdate, db: AsyncSession = Depends(get_db)
):
    cluster = await db.get(Cluster, cluster_id)
    if not cluster:
        raise HTTPException(404, "Cluster not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(cluster, field, value)
    await db.commit()
    await db.refresh(cluster)
    return cluster


@router.delete("/{cluster_id}", status_code=204)
async def delete_cluster(cluster_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """
    Deleting a Cluster row used to hit an unhandled IntegrityError as soon
    as it had any Deployment or NodePoolAssignment pointing at it -- those
    tables' foreign keys have no ON DELETE rule, so Postgres (which
    enforces FKs; SQLite doesn't unless told to, which is why this never
    showed up in dev/test) rejects the DELETE outright. Handle it properly
    instead of letting that surface as a raw 500:

    - refuse if a deployment is still in flight (deleting the cluster out
      from under a running Celery task is a real hazard, not just an FK
      technicality)
    - otherwise release any assigned hardware back to `available` (same
      as the per-asset /pools/{pool}/assets/{id} unassign path) and clean
      up the now-orphaned assignment/deployment rows before deleting the
      cluster itself
    """
    cluster = await db.get(Cluster, cluster_id)
    if not cluster:
        raise HTTPException(404, "Cluster not found")

    deployments = (
        await db.scalars(select(Deployment).where(Deployment.cluster_id == cluster_id))
    ).all()
    active = [d for d in deployments if d.phase not in _TERMINAL_PHASES]
    if active:
        raise HTTPException(
            409,
            f"Cluster has {len(active)} deployment(s) still in progress "
            f"(phase={active[0].phase.value}) -- wait for them to finish or fail first",
        )

    assignments = (
        await db.scalars(select(NodePoolAssignment).where(NodePoolAssignment.cluster_id == cluster_id))
    ).all()
    for assignment in assignments:
        asset = await db.get(HardwareAsset, assignment.asset_id)
        if asset:
            asset.status = AssetStatus.AVAILABLE
            asset.cluster_id = None
            asset.node_pool_name = None
        await db.delete(assignment)

    for deployment in deployments:
        await db.delete(deployment)

    # Machine rows aren't created by anything yet (api/machines.py only
    # proxies to the live K8s API), but the FK is there and not nullable --
    # covering it now avoids the exact same class of bug resurfacing the
    # day local Machine persistence gets wired up.
    machines = (await db.scalars(select(Machine).where(Machine.cluster_id == cluster_id))).all()
    for machine in machines:
        await db.delete(machine)

    await db.delete(cluster)
    await db.commit()
