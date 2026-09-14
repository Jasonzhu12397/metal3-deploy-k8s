from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.cluster import Cluster
from app.schemas.addon import AddonCatalogItem, AddonToggleResult
from app.services.addon_catalog import ADDON_BY_NAME, ADDON_CATALOG
from app.services.addons import INSTALL_METHODS
from app.tasks.addon_tasks import install_addon_task

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
    what the app-store grid renders (checked vs. install-able cards) --
    plus install_status/install_message from the real, most recent
    install attempt (tasks/addon_tasks.py), if any."""
    cluster = await _get_cluster(cluster_id, db)
    enabled = set(cluster.spec.get("addons", []))
    status_by_name = cluster.addon_status or {}
    return [
        AddonCatalogItem(
            **a,
            enabled=a["name"] in enabled,
            install_status=status_by_name.get(a["name"], {}).get("status"),
            install_message=status_by_name.get(a["name"], {}).get("message"),
        )
        for a in ADDON_CATALOG
    ]


@router.post("/clusters/{cluster_id}/addons/{addon_name}/enable", response_model=AddonToggleResult)
async def enable_addon(cluster_id: uuid.UUID, addon_name: str, db: AsyncSession = Depends(get_db)):
    """Records intent (spec.addons) AND, unlike before, actually attempts
    a real install against this cluster's live target kubeconfig right
    now -- not just "the next time this cluster gets (re)deployed from
    scratch", which for an already-running cluster could be never.

    Deliberately does not pre-check whether the cluster looks "ready"
    (e.g. cluster.status) before triggering -- same reasoning as
    api/ai_workloads.py's redeploy endpoint: just attempt the real
    operation and let it fail with a real, specific reason (recorded in
    addon_status, surfaced back through list_cluster_addons) if the
    target kubeconfig isn't there yet, rather than trusting a
    potentially-stale status field to predict that in advance.
    """
    if addon_name not in ADDON_BY_NAME:
        raise HTTPException(404, f"Unknown addon '{addon_name}'")
    if addon_name not in INSTALL_METHODS:
        # Unlike "target kubeconfig not ready yet" (a timing issue any
        # addon can hit, worth an async attempt-and-report), "no install
        # method wired up" is a deterministic, permanent fact about this
        # addon (see services/addons.py's own docstring for exactly
        # which of the 20 catalog entries have one) -- worth a clear,
        # synchronous 400 instead of queuing a task guaranteed to fail
        # and making the user go check its status separately to find
        # out why.
        raise HTTPException(
            400,
            f"'{addon_name}' has no real install method wired up yet (see services/addons.py) -- "
            f"enabling it would only record intent, not actually install anything.",
        )
    cluster = await _get_cluster(cluster_id, db)
    addons = set(cluster.spec.get("addons", []))
    addons.add(addon_name)
    cluster.spec = {**cluster.spec, "addons": sorted(addons)}
    await db.commit()

    install_addon_task.delay(str(cluster_id), addon_name)
    return AddonToggleResult(cluster_id=str(cluster_id), name=addon_name, enabled=True, install_triggered=True)


@router.delete("/clusters/{cluster_id}/addons/{addon_name}/disable", response_model=AddonToggleResult)
async def disable_addon(cluster_id: uuid.UUID, addon_name: str, db: AsyncSession = Depends(get_db)):
    cluster = await _get_cluster(cluster_id, db)
    addons = set(cluster.spec.get("addons", []))
    addons.discard(addon_name)
    cluster.spec = {**cluster.spec, "addons": sorted(addons)}
    await db.commit()
    return AddonToggleResult(cluster_id=str(cluster_id), name=addon_name, enabled=False)
