"""
Binds a HardwareAsset into a cluster's node pool with the operator's
choices for CPU reservation / NIC role mapping / disk role mapping --
i.e. exactly what gets picked in the UI ("this box goes in pool4,
these 2 NICs are the SR-IOV pair, reserve 4 cores/socket").
"""
from __future__ import annotations

from sqlalchemy import ForeignKey, String, Integer, Boolean, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedModel


class NodePoolAssignment(TimestampedModel):
    __tablename__ = "node_pool_assignments"

    cluster_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clusters.id"))
    pool_name: Mapped[str] = mapped_column(String(128))
    asset_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hardware_assets.id"))
    role: Mapped[str] = mapped_column(String(32), default="worker")  # worker | control-plane

    # --- CPU isolation ---
    reserved_cores_per_socket: Mapped[int] = mapped_column(Integer, default=4)
    cpu_manager_policy: Mapped[str] = mapped_column(String(32), default="static")
    topology_manager_policy: Mapped[str] = mapped_column(String(32), default="single-numa-node")
    isolation_interrupts: Mapped[bool] = mapped_column(Boolean, default=False)

    # --- Hugepages ---
    hugepage_type: Mapped[str] = mapped_column(String(16), default="1GB")
    hugepage_count_1gb: Mapped[int] = mapped_column(Integer, default=16)
    hugepage_count_2mb: Mapped[int] = mapped_column(Integer, default=0)

    # --- Optional manual overrides ---
    # If unset, roles are taken straight from HardwareAsset.nics[*].role /
    # HardwareAsset.disks[*].role (i.e. whatever was chosen when the asset
    # was picked for this pool in the UI).
    nic_role_overrides: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    disk_role_overrides: Mapped[dict | None] = mapped_column(JSON, nullable=True)
