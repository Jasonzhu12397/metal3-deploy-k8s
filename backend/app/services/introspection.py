"""
Turns Ironic hardware data into HardwareAsset fields, so nothing has to be
typed by hand once the BareMetalHost has been inspected.

Two data sources, richer one wins per field:

1. `BareMetalHost.status.hardware` (what baremetal-operator surfaces on the
   BMH object itself) -- always available once inspection completes, but
   does NOT include PCI address or NUMA node for NICs/disks.
2. Ironic's raw introspection ("inventory") data, e.g. from
   `GET /v1/introspection/{uuid}/data` on the Ironic API, or whatever your
   inspection webhook stores -- this is ironic-python-agent's own inventory
   format and DOES include `pci_address` / `numa_node` per interface, which
   is what the CAPI Metal3MachineTemplate / NMState net_config needs to
   pin bonds to specific PCI functions.

Callers that only have (1) still get usable results (kernel NIC names,
speeds, disk sizes/models, CPU count/model, RAM) -- PCI address and NUMA
node just come back as None and must be filled in via the UI before the
asset can be used to render network config.
"""
from __future__ import annotations

from typing import Any


def parse_bmh_hardware(status_hardware: dict[str, Any]) -> dict[str, Any]:
    cpu = status_hardware.get("cpu", {}) or {}
    nics_out = []
    for nic in status_hardware.get("nics", []) or []:
        nics_out.append(
            {
                "pci_address": None,  # not present in BMH.status.hardware; see module docstring
                "kernel_name": nic.get("name"),
                "model": nic.get("model"),
                "speed_gbps": nic.get("speedGbps"),
                "numa_node": None,
                "mtu": 9000,
                "sriov_capable": False,
                "total_vfs": 0,
                "role": "unassigned",
            }
        )

    disks_out = []
    for disk in status_hardware.get("storage", []) or []:
        size_bytes = disk.get("sizeBytes") or 0
        disks_out.append(
            {
                "device": disk.get("name"),
                "model": disk.get("model"),
                "size_gb": round(size_bytes / 1_000_000_000, 1) if size_bytes else None,
                "media_type": "hdd" if disk.get("rotational") else "ssd",
                "role": "unassigned",
            }
        )

    system_vendor = status_hardware.get("systemVendor", {}) or {}

    # cpu.count from BMH status is *logical* CPU count; without socket/core
    # breakdown we make a conservative single-socket assumption and flag it
    # so the UI can prompt the operator to correct it (or better: supply
    # ironic introspection data via enrich_with_ironic_inventory below).
    logical = cpu.get("count") or 0
    return {
        "vendor": system_vendor.get("manufacturer"),
        "model": system_vendor.get("productName"),
        "serial_number": system_vendor.get("serialNumber"),
        "cpu_model": cpu.get("model"),
        "cpu_sockets": 1,
        "cpu_cores_per_socket": logical // 2 if logical else 0,  # assumes SMT=2, single socket
        "cpu_threads_per_core": 2,
        "memory_gb": round((status_hardware.get("ramMebibytes") or 0) / 1024, 1),
        "nics": nics_out,
        "disks": disks_out,
    }


def enrich_with_ironic_inventory(
    base_fields: dict[str, Any], inventory: dict[str, Any]
) -> dict[str, Any]:
    """`inventory` is ironic-python-agent's raw inventory dict (has
    'cpu', 'memory', 'interfaces', 'disks' top-level keys with PCI/NUMA
    detail). Overwrites/augments what parse_bmh_hardware produced."""
    cpu = inventory.get("cpu", {}) or {}
    # ironic-python-agent reports total logical count; socket topology
    # itself typically has to come from `cpu.get("socket_count")` if your
    # IPA build exposes it (not all do) -- fall back gracefully.
    socket_count = cpu.get("socket_count") or base_fields.get("cpu_sockets", 1)
    threads_per_core = 2 if cpu.get("flags") and "ht" in (cpu.get("flags") or []) else base_fields.get(
        "cpu_threads_per_core", 2
    )
    total_logical = cpu.get("count") or 0
    cores_per_socket = (
        (total_logical // (socket_count * threads_per_core))
        if total_logical and socket_count and threads_per_core
        else 0
    )

    interfaces = []
    for iface in inventory.get("interfaces", []) or []:
        interfaces.append(
            {
                "pci_address": iface.get("pci_address"),
                "kernel_name": iface.get("name"),
                "model": iface.get("product") or iface.get("vendor"),
                "speed_gbps": (iface.get("current_speed_mbps") or 0) / 1000 or None,
                "numa_node": iface.get("numa_node"),
                "mtu": 9000,
                "sriov_capable": bool(iface.get("sriov_totalvfs")),
                "total_vfs": iface.get("sriov_totalvfs") or 0,
                "role": "unassigned",
            }
        )

    disks = []
    for disk in inventory.get("disks", []) or []:
        size_bytes = disk.get("size") or 0
        disks.append(
            {
                "device": disk.get("name") or disk.get("by_path"),
                "model": disk.get("model"),
                "size_gb": round(size_bytes / 1_000_000_000, 1) if size_bytes else None,
                "media_type": "nvme" if "nvme" in (disk.get("name") or "") else (
                    "hdd" if disk.get("rotational") else "ssd"
                ),
                "role": "unassigned",
            }
        )

    merged = dict(base_fields)
    merged.update(
        {
            "cpu_sockets": socket_count or base_fields.get("cpu_sockets", 1),
            "cpu_cores_per_socket": cores_per_socket or base_fields.get("cpu_cores_per_socket", 0),
            "cpu_threads_per_core": threads_per_core,
            "memory_gb": round((inventory.get("memory", {}).get("physical_mb") or 0) / 1024, 1)
            or base_fields.get("memory_gb", 0),
        }
    )
    if interfaces:
        merged["nics"] = interfaces
    if disks:
        merged["disks"] = disks
    return merged
