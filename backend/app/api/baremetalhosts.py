from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.hardware_asset import AssetStatus, HardwareAsset
from app.schemas.baremetalhost import (
    BareMetalHostBulkImport,
    BareMetalHostCreate,
    BareMetalHostRead,
)
from app.services.metal3 import Metal3Service

router = APIRouter(prefix="/baremetalhosts", tags=["baremetalhosts"])
metal3_service = Metal3Service()


async def _upsert_hardware_asset_shell(payload: BareMetalHostCreate, db: AsyncSession) -> None:
    """BMC address / boot MAC / pool are known at registration time and
    never come from Ironic inspection -- so rather than making the caller
    duplicate this data into a separate `POST /hardware-assets` call, we
    seed (or update) the matching HardwareAsset row here. CPU/NIC/disk
    fields stay empty until `POST /hardware-assets/{id}/sync-from-ironic`
    runs after inspection completes."""
    existing = await db.scalar(select(HardwareAsset).where(HardwareAsset.name == payload.name))
    if existing:
        existing.bmc_address = payload.bmc_address
        existing.boot_mac_address = payload.boot_mac_address
        existing.node_pool_name = payload.node_pool_name
    else:
        db.add(
            HardwareAsset(
                name=payload.name,
                bmc_address=payload.bmc_address,
                boot_mac_address=payload.boot_mac_address,
                node_pool_name=payload.node_pool_name,
                status=AssetStatus.DISCOVERED,
            )
        )
    await db.commit()


@router.post("", status_code=201)
async def register_host(payload: BareMetalHostCreate, db: AsyncSession = Depends(get_db)):
    try:
        result = metal3_service.register_host(payload)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Failed to register host: {exc}") from exc
    await _upsert_hardware_asset_shell(payload, db)
    return {"name": payload.name, "applied": True, "resourceVersion": result["metadata"].get("resourceVersion")}


@router.post("/bulk-import", status_code=201)
async def bulk_import(payload: BareMetalHostBulkImport, db: AsyncSession = Depends(get_db)):
    """Registers many hosts at once -- e.g. everything parsed out of a
    bmhosts.yaml-style file (BMC creds must be supplied fresh via the API,
    not read back out of that file)."""
    try:
        results = metal3_service.bulk_register(payload.hosts)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Bulk import failed: {exc}") from exc
    for host in payload.hosts:
        await _upsert_hardware_asset_shell(host, db)
    return {"registered": [h.name for h in payload.hosts], "count": len(results)}


@router.get("")
async def list_hosts(node_pool: str | None = None):
    return metal3_service.list_hosts(node_pool=node_pool)


@router.get("/{name}/status")
async def host_status(name: str):
    status = metal3_service.get_host_status(name)
    if status is None:
        raise HTTPException(404, "Host not found")
    return status


@router.post("/{name}/power")
async def set_power(name: str, online: bool):
    try:
        metal3_service.set_power_state(name, online)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"name": name, "online": online}
