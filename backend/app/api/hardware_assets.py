from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.hardware_asset import AssetStatus, HardwareAsset
from app.schemas.hardware_asset import (
    HardwareAssetCreate,
    HardwareAssetRead,
    HardwareAssetUpdate,
)
from app.services.introspection import enrich_with_ironic_inventory, parse_bmh_hardware
from app.services.metal3 import Metal3Service

router = APIRouter(prefix="/hardware-assets", tags=["hardware-assets"])
metal3_service = Metal3Service()


@router.post("", response_model=HardwareAssetRead, status_code=201)
async def create_asset(payload: HardwareAssetCreate, db: AsyncSession = Depends(get_db)):
    """Manual/dry-run registration. Prefer POST /{name}/sync-from-ironic
    once the matching BareMetalHost has completed inspection."""
    existing = await db.scalar(select(HardwareAsset).where(HardwareAsset.name == payload.name))
    if existing:
        raise HTTPException(409, f"Asset '{payload.name}' already exists")
    asset = HardwareAsset(
        **payload.model_dump(exclude={"nics", "disks"}),
        nics=[n.model_dump() for n in payload.nics],
        disks=[d.model_dump() for d in payload.disks],
        status=AssetStatus.DISCOVERED,
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return asset


@router.get("", response_model=list[HardwareAssetRead])
async def list_assets(
    status: AssetStatus | None = None,
    unassigned_only: bool = False,
    min_memory_gb: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(HardwareAsset)
    if status:
        query = query.where(HardwareAsset.status == status)
    if unassigned_only:
        query = query.where(HardwareAsset.cluster_id.is_(None))
    if min_memory_gb:
        query = query.where(HardwareAsset.memory_gb >= min_memory_gb)
    result = await db.scalars(query.order_by(HardwareAsset.name))
    return result.all()


@router.get("/{asset_id}", response_model=HardwareAssetRead)
async def get_asset(asset_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    asset = await db.get(HardwareAsset, asset_id)
    if not asset:
        raise HTTPException(404, "Asset not found")
    return asset


@router.patch("/{asset_id}", response_model=HardwareAssetRead)
async def update_asset(
    asset_id: uuid.UUID, payload: HardwareAssetUpdate, db: AsyncSession = Depends(get_db)
):
    """Used by the UI to set/correct NIC and disk roles (which PCI function
    is bond_control vs bond_data vs SR-IOV, which disk is OS vs Ceph OSD)."""
    asset = await db.get(HardwareAsset, asset_id)
    if not asset:
        raise HTTPException(404, "Asset not found")
    data = payload.model_dump(exclude_unset=True)
    if "nics" in data and data["nics"] is not None:
        data["nics"] = [n if isinstance(n, dict) else n.model_dump() for n in data["nics"]]
    if "disks" in data and data["disks"] is not None:
        data["disks"] = [d if isinstance(d, dict) else d.model_dump() for d in data["disks"]]
    for field, value in data.items():
        setattr(asset, field, value)
    await db.commit()
    await db.refresh(asset)
    return asset


@router.delete("/{asset_id}", status_code=204)
async def delete_asset(asset_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    asset = await db.get(HardwareAsset, asset_id)
    if not asset:
        raise HTTPException(404, "Asset not found")
    await db.delete(asset)
    await db.commit()


@router.post("/{asset_id}/sync-from-ironic", response_model=HardwareAssetRead)
async def sync_from_ironic(
    asset_id: uuid.UUID,
    ironic_inventory: dict | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Pulls CPU/RAM/NIC/disk data from the matching BareMetalHost's
    Ironic-driven `status.hardware`. Optionally pass the raw Ironic
    introspection `inventory` dict (has PCI address + NUMA node per NIC,
    which BMH.status.hardware alone does not) to get a fully-populated
    asset in one call instead of having to fill in PCI addresses by hand
    afterwards."""
    asset = await db.get(HardwareAsset, asset_id)
    if not asset:
        raise HTTPException(404, "Asset not found")

    hardware = metal3_service.get_hardware_details(asset.name)
    if not hardware:
        raise HTTPException(
            409, f"BareMetalHost '{asset.name}' has no status.hardware yet -- inspection incomplete"
        )

    fields = parse_bmh_hardware(hardware)
    if ironic_inventory:
        fields = enrich_with_ironic_inventory(fields, ironic_inventory)

    for field, value in fields.items():
        setattr(asset, field, value)
    asset.status = AssetStatus.AVAILABLE
    await db.commit()
    await db.refresh(asset)
    return asset
