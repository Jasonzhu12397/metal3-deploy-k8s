from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.cluster import Cluster
from app.schemas.addon import AddonCatalogItem, AddonToggleResult
from app.services.addon_catalog import ADDON_BY_NAME, ADDON_CATALOG

router = APIRouter(tags=["addons"])


@router.get("/addons/catalog", response_model=list[AddonCatalogItem])
async def addon_catalog():
    """The full app-store catalog, cluster-agnostic."""
    return [AddonCatalogItem(**a) for a in ADDON_CATALOG]


async def _get_cluster(cluster_id: uuid.UUID, db: AsyncSession) -> Cluster:
    cluster = await db.get(Cluster, cluster_id)
    if not cluster:
        raise HTTPException(404, "Cluster not found")
    return cluster


@router.get("/clusters/{cluster_id}/addons", response_model=list[AddonCatalogItem])
async def list_cluster_addons(cluster_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Catalog with `enabled` reflecting this cluster's spec.addons list --
    what the app-store grid renders (checked vs. install-able cards)."""
    cluster = await _get_cluster(cluster_id, db)
    enabled = set(cluster.spec.get("addons", []))
    return [AddonCatalogItem(**a, enabled=a["name"] in enabled) for a in ADDON_CATALOG]


@router.post("/clusters/{cluster_id}/addons/{addon_name}/enable", response_model=AddonToggleResult)
async def enable_addon(cluster_id: uuid.UUID, addon_name: str, db: AsyncSession = Depends(get_db)):
    if addon_name not in ADDON_BY_NAME:
        raise HTTPException(404, f"Unknown addon '{addon_name}'")
    cluster = await _get_cluster(cluster_id, db)
    addons = set(cluster.spec.get("addons", []))
    addons.add(addon_name)
    cluster.spec = {**cluster.spec, "addons": sorted(addons)}
    await db.commit()
    return AddonToggleResult(cluster_id=str(cluster_id), name=addon_name, enabled=True)


@router.delete("/clusters/{cluster_id}/addons/{addon_name}/disable", response_model=AddonToggleResult)
async def disable_addon(cluster_id: uuid.UUID, addon_name: str, db: AsyncSession = Depends(get_db)):
    cluster = await _get_cluster(cluster_id, db)
    addons = set(cluster.spec.get("addons", []))
    addons.discard(addon_name)
    cluster.spec = {**cluster.spec, "addons": sorted(addons)}
    await db.commit()
    return AddonToggleResult(cluster_id=str(cluster_id), name=addon_name, enabled=False)
