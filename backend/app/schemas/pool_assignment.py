from __future__ import annotations

import uuid
from typing import Optional

from pydantic import BaseModel, Field


class PoolAssignRequest(BaseModel):
    asset_ids: list[uuid.UUID]
    role: str = "worker"  # worker | control-plane
    reserved_cores_per_socket: int = 4
    cpu_manager_policy: str = "static"
    topology_manager_policy: str = "single-numa-node"
    isolation_interrupts: bool = False
    hugepage_type: str = "1GB"
    hugepage_count_1gb: int = 16
    hugepage_count_2mb: int = 0
    nic_role_overrides: Optional[dict] = None
    disk_role_overrides: Optional[dict] = None


class PoolAssignmentRead(BaseModel):
    id: uuid.UUID
    cluster_id: uuid.UUID
    pool_name: str
    asset_id: uuid.UUID
    role: str
    reserved_cores_per_socket: int
    cpu_manager_policy: str
    topology_manager_policy: str
    isolation_interrupts: bool
    hugepage_type: str
    hugepage_count_1gb: int
    hugepage_count_2mb: int
    computed_reserved_cpus: str = ""
    computed_isolated_cpu_count: int = 0

    class Config:
        from_attributes = True


class ClusterManifestBundle(BaseModel):
    """Everything the system generated -- nothing hand-typed."""

    bmh_yaml: str
    cluster_config_yaml: str
    network_policies: dict[str, str] = Field(default_factory=dict)  # pool_name -> yaml
    eph_net_yaml: Optional[str] = None
