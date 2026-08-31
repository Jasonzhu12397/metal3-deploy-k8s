from __future__ import annotations

import uuid
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.models.hardware_asset import AssetStatus, DiskRole, NicRole


class NicSpec(BaseModel):
    pci_address: str  # e.g. "0000:37:00.0"
    kernel_name: Optional[str] = None  # e.g. "enp55s0f0np0", filled in after boot/introspection
    model: Optional[str] = None  # e.g. "Mellanox ConnectX-6 Dx"
    speed_gbps: Optional[float] = None
    numa_node: Optional[int] = None
    mtu: int = 9000
    sriov_capable: bool = False
    total_vfs: int = 0
    role: NicRole = NicRole.UNASSIGNED


class DiskSpec(BaseModel):
    device: Optional[str] = None  # e.g. "/dev/nvme0n1" or a by-id path
    model: Optional[str] = None  # e.g. "Dell Ent NVMe CM7 U.2 3.2TB"
    size_gb: Optional[float] = None
    media_type: str = "nvme"  # nvme | ssd | hdd
    role: DiskRole = DiskRole.UNASSIGNED


class HardwareAssetCreate(BaseModel):
    name: str
    serial_number: Optional[str] = None
    vendor: Optional[str] = None
    model: Optional[str] = None
    cpu_model: Optional[str] = None
    cpu_sockets: int = 2
    cpu_cores_per_socket: int = 32
    cpu_threads_per_core: int = 2
    memory_gb: int = 0
    gpu_model: Optional[str] = None
    gpu_count: int = 0
    gpu_memory_gb: Optional[int] = None
    nics: list[NicSpec] = Field(default_factory=list)
    disks: list[DiskSpec] = Field(default_factory=list)
    bmc_address: Optional[str] = None
    boot_mac_address: Optional[str] = None


class HardwareAssetUpdate(BaseModel):
    status: Optional[AssetStatus] = None
    nics: Optional[list[NicSpec]] = None
    disks: Optional[list[DiskSpec]] = None
    node_pool_name: Optional[str] = None
    bmc_address: Optional[str] = None
    boot_mac_address: Optional[str] = None
    gpu_model: Optional[str] = None
    gpu_count: Optional[int] = None
    gpu_memory_gb: Optional[int] = None


class HardwareAssetRead(BaseModel):
    id: uuid.UUID
    name: str
    serial_number: Optional[str] = None
    vendor: Optional[str] = None
    model: Optional[str] = None
    status: AssetStatus
    cpu_model: Optional[str] = None
    cpu_sockets: int
    cpu_cores_per_socket: int
    cpu_threads_per_core: int
    memory_gb: int
    gpu_model: Optional[str] = None
    gpu_count: int = 0
    gpu_memory_gb: Optional[int] = None
    has_gpu: bool = False
    nics: list[dict]
    disks: list[dict]
    bmc_address: Optional[str] = None
    bmc_username: Optional[str] = None
    # Deliberately a boolean, never the encrypted (or, worse, decrypted)
    # password itself -- there's no legitimate reason for any API response
    # to carry that value back out, encrypted or not. Fetch the plaintext
    # server-side only, at the one point it's actually needed
    # (services/bmc.py writing the Kubernetes Secret).
    has_bmc_credentials: bool = False
    boot_mac_address: Optional[str] = None
    node_pool_name: Optional[str] = None
    cluster_id: Optional[uuid.UUID] = None

    class Config:
        from_attributes = True


class SetBmcCredentialsRequest(BaseModel):
    """Separate from HardwareAssetUpdate on purpose: setting a BMC password
    is a different, more sensitive operation than editing NIC roles, and
    deserves its own endpoint/audit trail rather than being one optional
    field among many on a general-purpose PATCH."""

    username: str
    password: str


class HardwareAssetFilter(BaseModel):
    status: Optional[AssetStatus] = None
    min_cpu_sockets: Optional[int] = None
    min_memory_gb: Optional[int] = None
    nic_model_contains: Optional[str] = None
    unassigned_only: bool = False
    has_gpu: Optional[bool] = None


class SyncFromIronicRequest(BaseModel):
    """A bare `dict | None` function parameter looks like it should bind to
    a JSON body of `{"ironic_inventory": {...}}` the way a Pydantic model
    field would, but FastAPI doesn't embed single non-model body params
    under their parameter name -- it expects the raw inventory object as
    the *entire* request body instead, with nothing wrapping it. Every
    caller (USAGE.md's documented curl example, and the frontend's
    api.hardwareAssets.syncFromIronic) already sends the wrapped shape, so
    the wrapped shape is the one true contract -- this model exists so
    FastAPI actually binds it instead of silently leaving it as `None`
    (which the old bare-dict parameter did: no error, just quietly
    skipping the enrichment step)."""

    ironic_inventory: Optional[dict[str, Any]] = None
