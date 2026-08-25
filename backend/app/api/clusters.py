from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.cluster import Cluster
from app.schemas.cluster import ClusterCreate, ClusterRead, ClusterUpdate

router = APIRouter(prefix="/clusters", tags=["clusters"])


@router.post("", response_model=ClusterRead, status_code=201)
async def create_cluster(payload: ClusterCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.scalar(select(Cluster).where(Cluster.name == payload.name))
    if existing:
        raise HTTPException(409, f"Cluster '{payload.name}' already exists")

    cluster = Cluster(
        name=payload.name,
        namespace=payload.namespace,
        control_plane_count=payload.control_plane_count,
        control_plane_endpoint=payload.control_plane_endpoint,
        worker_pool_config={"pools": [p.model_dump() for p in payload.worker_pools]},
        spec=payload.spec,
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
    cluster = await db.get(Cluster, cluster_id)
    if not cluster:
        raise HTTPException(404, "Cluster not found")
    await db.delete(cluster)
    await db.commit()
