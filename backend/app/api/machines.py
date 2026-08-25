from __future__ import annotations

from fastapi import APIRouter

from app.services.capi import CAPIService

router = APIRouter(prefix="/machines", tags=["machines"])
capi_service = CAPIService()


@router.get("")
async def list_machines(cluster_name: str, namespace: str = "metal3"):
    return capi_service.list_machines(cluster_name, namespace)
