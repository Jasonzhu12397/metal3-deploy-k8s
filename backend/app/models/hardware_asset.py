"""
Discovered/registered physical server inventory: CPU topology, memory,
NIC list (with PCI address + model + speed + NUMA node + assigned role),
and disk list (with model/size/media type + assigned role). This is the
thing a user picks from in the UI instead of typing PCI addresses or
reserved-CPU strings by hand.
"""
from __future__ import annotations

import enum

from sqlalchemy import JSON, String, Enum, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedModel


class AssetStatus(str, enum.Enum):
    DISCOVERED = "discovered"    # known to the system, not yet vetted
    AVAILABLE = "available"      # vetted, unassigned, ready to pick in the UI
    RESERVED = "reserved"        # assigned to a cluster/pool, not yet deployed
    PROVISIONED = "provisioned"  # actively running as part of a cluster
    DECOMMISSIONED = "decommissioned"


class NicRole(str, enum.Enum):
    CONTROL = "control"    # bond_control (kubeadm/API traffic, active-backup)
    DATA = "data"          # bond_data (pod/service traffic, LACP)
    STORAGE = "storage"    # bond_storage (Ceph replication, LACP)
    SRIOV = "sriov"        # individual SR-IOV capable PF (DPDK/high-throughput pools)
    UNASSIGNED = "unassigned"


class DiskRole(str, enum.Enum):
    OS = "os"
    CEPH_OSD = "ceph_osd"
    CEPH_JOURNAL = "ceph_journal"
    LOCAL_STORAGE = "local_storage"
    UNASSIGNED = "unassigned"


class HardwareAsset(TimestampedModel):
    """
    nics: list[{
      pci_address: "0000:37:00.0", kernel_name: "enp55s0f0np0"?,
      model: "Mellanox ConnectX-6 Dx", speed_gbps: 25, numa_node: 0,
      mtu: 9000, sriov_capable: bool, total_vfs: int, role: NicRole
    }]
    disks: list[{
      device: "/dev/nvme0n1"?, model: "Dell Ent NVMe CM7 U.2 3.2TB",
      size_gb: 3200, media_type: "nvme", role: DiskRole
    }]
    """

    __tablename__ = "hardware_assets"

    name: Mapped[str] = mapped_column(String(253), unique=True, index=True)
    serial_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    vendor: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)  # e.g. "Dell R660"
    status: Mapped[AssetStatus] = mapped_column(Enum(AssetStatus), default=AssetStatus.DISCOVERED)

    cpu_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    cpu_sockets: Mapped[int] = mapped_column(Integer, default=2)
    cpu_cores_per_socket: Mapped[int] = mapped_column(Integer, default=32)
    cpu_threads_per_core: Mapped[int] = mapped_column(Integer, default=2)

    memory_gb: Mapped[int] = mapped_column(Integer, default=0)

    nics: Mapped[list] = mapped_column(JSON, default=list)
    disks: Mapped[list] = mapped_column(JSON, default=list)

    bmc_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    boot_mac_address: Mapped[str | None] = mapped_column(String(17), nullable=True)

    node_pool_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    cluster_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clusters.id", ondelete="SET NULL"), nullable=True
    )

    @property
    def total_physical_cores(self) -> int:
        return self.cpu_sockets * self.cpu_cores_per_socket

    @property
    def total_logical_cpus(self) -> int:
        return self.total_physical_cores * self.cpu_threads_per_core
