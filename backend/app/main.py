from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    addons,
    baremetalhosts,
    bmc,
    clusters,
    deployments,
    hardware_assets,
    health,
    machines,
    manifests,
    planner,
)
from app.core.config import get_settings
from app.core.db import init_db
from app.core.logging import configure_logging

settings = get_settings()
configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(clusters.router, prefix=settings.API_V1_PREFIX)
app.include_router(baremetalhosts.router, prefix=settings.API_V1_PREFIX)
app.include_router(bmc.router, prefix=settings.API_V1_PREFIX)
app.include_router(machines.router, prefix=settings.API_V1_PREFIX)
app.include_router(deployments.router, prefix=settings.API_V1_PREFIX)
app.include_router(manifests.router, prefix=settings.API_V1_PREFIX)
app.include_router(hardware_assets.router, prefix=settings.API_V1_PREFIX)
app.include_router(planner.router, prefix=settings.API_V1_PREFIX)
app.include_router(addons.router, prefix=settings.API_V1_PREFIX)


@app.get("/")
async def root():
    return {"service": settings.APP_NAME, "docs": "/docs"}
