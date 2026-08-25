from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz():
    return {"status": "ok"}


@router.get("/readyz")
async def readyz():
    # Extend with real DB/redis/mgmt-cluster reachability checks as needed.
    return {"status": "ready"}
