from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    addons,
    auth,
    baremetalhosts,
    bmc,
    clusters,
    deployments,
    hardware_assets,
    health,
    llm_providers,
    machines,
    manifests,
    planner,
)
from app.core.config import get_settings
from app.core.db import AsyncSessionLocal, init_db
from app.core.logging import configure_logging
from app.core.security import get_current_subject
from app.services.auth import ensure_seed_admin

settings = get_settings()
configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with AsyncSessionLocal() as session:
        await ensure_seed_admin(session)
    yield


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# /healthz, /readyz, and POST /auth/login stay open -- everything else
# requires a bearer token. auth.router protects /me and /change-password
# per-route internally (login has to stay reachable while logged out).
authed = [Depends(get_current_subject)]

app.include_router(health.router)
app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(clusters.router, prefix=settings.API_V1_PREFIX, dependencies=authed)
app.include_router(baremetalhosts.router, prefix=settings.API_V1_PREFIX, dependencies=authed)
app.include_router(bmc.router, prefix=settings.API_V1_PREFIX, dependencies=authed)
app.include_router(machines.router, prefix=settings.API_V1_PREFIX, dependencies=authed)
app.include_router(deployments.router, prefix=settings.API_V1_PREFIX, dependencies=authed)
app.include_router(deployments.ws_router, prefix=settings.API_V1_PREFIX)
app.include_router(manifests.router, prefix=settings.API_V1_PREFIX, dependencies=authed)
app.include_router(hardware_assets.router, prefix=settings.API_V1_PREFIX, dependencies=authed)
app.include_router(planner.router, prefix=settings.API_V1_PREFIX, dependencies=authed)
app.include_router(addons.router, prefix=settings.API_V1_PREFIX, dependencies=authed)
app.include_router(llm_providers.router, prefix=settings.API_V1_PREFIX, dependencies=authed)


@app.get("/")
async def root():
    return {"service": settings.APP_NAME, "docs": "/docs"}
