from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.hardware_asset import AssetStatus, HardwareAsset
from app.schemas.baremetalhost import BMCCredentials
from app.schemas.hardware_asset import (
    HardwareAssetCreate,
    HardwareAssetRead,
    HardwareAssetUpdate,
    SetBmcCredentialsRequest,
    SyncFromIronicRequest,
)
from app.services import crypto
from app.services.bmc import BMCService
from app.services.introspection import enrich_with_ironic_inventory, parse_bmh_hardware
from app.services.metal3 import Metal3Service

router = APIRouter(prefix="/hardware-assets", tags=["hardware-assets"])
metal3_service = Metal3Service()
bmc_service = BMCService()


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
    payload: SyncFromIronicRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Pulls CPU/RAM/NIC/disk data from the matching BareMetalHost's
    Ironic-driven `status.hardware`. Optionally pass
    `{"ironic_inventory": {...}}` (the raw Ironic introspection inventory
    dict -- has PCI address + NUMA node per NIC, which BMH.status.hardware
    alone does not) to get a fully-populated asset in one call instead of
    having to fill in PCI addresses by hand afterwards."""
    asset = await db.get(HardwareAsset, asset_id)
    if not asset:
        raise HTTPException(404, "Asset not found")

    ironic_inventory = payload.ironic_inventory if payload else None
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


@router.post("/{asset_id}/bmc-credentials", response_model=HardwareAssetRead)
async def set_bmc_credentials(
    asset_id: uuid.UUID, payload: SetBmcCredentialsRequest, db: AsyncSession = Depends(get_db)
):
    """Encrypts and stores BMC credentials against an asset that wasn't
    necessarily registered through POST /baremetalhosts (which does this
    automatically) -- e.g. backfilling credentials for hardware that was
    onboarded some other way. Immediately (re)writes the Kubernetes Secret
    too, the same as registration does, so this and the BMH-registration
    path can't drift into storing different passwords than what Metal3
    actually has."""
    asset = await db.get(HardwareAsset, asset_id)
    if not asset:
        raise HTTPException(404, "Asset not found")

    try:
        encrypted = crypto.encrypt_secret(payload.password)
    except crypto.EncryptionKeyNotConfigured as exc:
        raise HTTPException(500, str(exc)) from exc

    try:
        bmc_service.store_credentials(asset.name, BMCCredentials(**payload.model_dump()))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Stored encrypted locally, but failed to write the Kubernetes Secret: {exc}") from exc

    asset.bmc_username = payload.username
    asset.encrypted_bmc_password = encrypted
    await db.commit()
    await db.refresh(asset)
    return asset


@router.post("/{asset_id}/resync-bmc-secret")
async def resync_bmc_secret(asset_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Decrypts the stored BMC password and re-writes the Kubernetes
    Secret from it -- for when that Secret got deleted, the namespace got
    recreated, or you're just not sure it's still in sync. Never returns
    the password itself; only confirms the write happened."""
    asset = await db.get(HardwareAsset, asset_id)
    if not asset:
        raise HTTPException(404, "Asset not found")
    if not asset.has_bmc_credentials or not asset.bmc_username:
        raise HTTPException(409, "No BMC credentials are stored for this asset")

    try:
        password = crypto.decrypt_secret(asset.encrypted_bmc_password)
    except crypto.EncryptionKeyNotConfigured as exc:
        raise HTTPException(500, str(exc)) from exc
    except crypto.InvalidToken as exc:
        raise HTTPException(
            500,
            "Stored credential could not be decrypted with the configured BMC_ENCRYPTION_KEY "
            "-- likely the key was rotated/changed without re-encrypting this row first.",
        ) from exc

    secret_name = bmc_service.store_credentials(asset.name, BMCCredentials(username=asset.bmc_username, password=password))
    return {"asset_id": str(asset_id), "secret_name": secret_name, "resynced": True}
