from __future__ import annotations

import uuid
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.models.cluster import ClusterStatus


class WorkerPoolSpec(BaseModel):
    name: str
    count: int
    role: str = "worker"
    node_labels: list[str] = Field(default_factory=list)
    hugepage_type: Optional[str] = None
    reserved_cpus: Optional[str] = None


class ClusterCreate(BaseModel):
    name: str = Field(..., description="Cluster name, e.g. pk-cnis-pcg")
    namespace: str = "metal3"
    control_plane_count: int = 3
    control_plane_endpoint: Optional[str] = None
    worker_pools: list[WorkerPoolSpec] = Field(default_factory=list)
    # Arbitrary extra spec (pod/service CIDRs, networks, iaas, etc.)
    # mirroring the ccdadm-config.yaml structure the user already has.
    spec: dict[str, Any] = Field(default_factory=dict)


class ClusterRead(BaseModel):
    id: uuid.UUID
    name: str
    namespace: str
    status: ClusterStatus
    control_plane_endpoint: Optional[str] = None
    control_plane_count: int
    worker_pool_config: dict[str, Any]
    spec: dict[str, Any] = Field(default_factory=dict)

    class Config:
        from_attributes = True


class ClusterUpdate(BaseModel):
    control_plane_endpoint: Optional[str] = None
    status: Optional[ClusterStatus] = None
