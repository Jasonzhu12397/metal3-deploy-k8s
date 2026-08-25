"""
Renders the three artefacts described by the user's original layout:
bmh.yaml, k8s-config.yaml, eph-net.yaml -- from structured JSON input
instead of hand-edited YAML, so they can be regenerated deterministically
per-cluster and kept out of version control (they may embed
environment-specific network/BMC details).
"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from app.services.yaml_generator import YamlGeneratorService

router = APIRouter(prefix="/manifests", tags=["manifests"])
yaml_gen = YamlGeneratorService()


class BMHRenderRequest(BaseModel):
    hosts: list[dict]


class ClusterRenderRequest(BaseModel):
    cluster: dict


class NetRenderRequest(BaseModel):
    net: dict


@router.post("/bmh", response_class=PlainTextResponse)
async def render_bmh(payload: BMHRenderRequest):
    return yaml_gen.render_bmh(payload.hosts)


@router.post("/cluster-config", response_class=PlainTextResponse)
async def render_cluster_config(payload: ClusterRenderRequest):
    return yaml_gen.render_cluster_config(payload.cluster)


@router.post("/eph-net", response_class=PlainTextResponse)
async def render_eph_net(payload: NetRenderRequest):
    return yaml_gen.render_ephemeral_network(payload.net)
