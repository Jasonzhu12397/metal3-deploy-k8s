"""
Covers app/services/introspection.py -- found via `ruff check` during a
bug-scanning pass to have ZERO test coverage despite doing real,
non-trivial computation (unit conversions, CPU topology math from raw
Ironic/ironic-python-agent data shapes). That scan surfaced a real,
reachable crash (see test_threads_per_core_zero_does_not_crash below)
that had shipped silently until now.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.services.introspection import (  # noqa: E402
    enrich_with_ironic_inventory,
    parse_bmh_hardware,
)


# A realistic BareMetalHost.status.hardware shape, matching what
# baremetal-operator actually surfaces (see this module's own docstring
# for the two-data-source distinction this file is built around).
REALISTIC_BMH_HARDWARE = {
    "systemVendor": {
        "manufacturer": "Dell Inc.",
        "productName": "PowerEdge R750",
        "serialNumber": "ABC123XYZ",
    },
    "cpu": {"count": 64, "model": "Intel(R) Xeon(R) Gold 6338"},
    "ramMebibytes": 262144,  # 256 GiB
    "nics": [
        {"name": "eth0", "model": "Broadcom BCM5720", "speedGbps": 1},
        {"name": "eth1", "model": "Mellanox ConnectX-6", "speedGbps": 100},
    ],
    "storage": [
        {"name": "/dev/sda", "model": "PERC H740P", "sizeBytes": 960_000_000_000, "rotational": False},
        {"name": "/dev/sdb", "model": "Seagate Exos", "sizeBytes": 4_000_000_000_000, "rotational": True},
    ],
}

# A realistic ironic-python-agent inventory shape (the richer data
# source, from raw introspection rather than what baremetal-operator
# summarizes onto the BMH object).
REALISTIC_IPA_INVENTORY = {
    "cpu": {"count": 64, "socket_count": 2, "model_name": "Intel(R) Xeon(R) Gold 6338", "flags": ["ht", "avx512f"]},
    "memory": {"physical_mb": 262144},
    "interfaces": [
        {
            "name": "enp55s0f0np0",
            "pci_address": "0000:37:00.0",
            "product": "MT2892 Family [ConnectX-6 Dx]",
            "vendor": "Mellanox",
            "current_speed_mbps": 100000,
            "numa_node": 0,
            "sriov_totalvfs": 8,
        },
    ],
    "disks": [
        {"name": "nvme0n1", "model": "Dell Ent NVMe CM7", "size": 3_200_000_000_000, "rotational": False},
    ],
}


def test_parse_bmh_hardware_extracts_vendor_and_serial():
    result = parse_bmh_hardware(REALISTIC_BMH_HARDWARE)
    assert result["vendor"] == "Dell Inc."
    assert result["model"] == "PowerEdge R750"
    assert result["serial_number"] == "ABC123XYZ"
    assert result["cpu_model"] == "Intel(R) Xeon(R) Gold 6338"


def test_parse_bmh_hardware_memory_conversion_mebibytes_to_gb():
    result = parse_bmh_hardware(REALISTIC_BMH_HARDWARE)
    assert result["memory_gb"] == 256.0


def test_parse_bmh_hardware_conservative_single_socket_assumption():
    """No socket/core breakdown in BMH.status.hardware -- confirms the
    documented conservative fallback (single socket, SMT=2) instead of
    silently guessing something else."""
    result = parse_bmh_hardware(REALISTIC_BMH_HARDWARE)
    assert result["cpu_sockets"] == 1
    assert result["cpu_threads_per_core"] == 2
    assert result["cpu_cores_per_socket"] == 32  # 64 logical / 2 (SMT) / 1 socket


def test_parse_bmh_hardware_disk_size_conversion_bytes_to_gb():
    result = parse_bmh_hardware(REALISTIC_BMH_HARDWARE)
    disks = {d["device"]: d for d in result["disks"]}
    assert disks["/dev/sda"]["size_gb"] == 960.0
    assert disks["/dev/sda"]["media_type"] == "ssd"
    assert disks["/dev/sdb"]["size_gb"] == 4000.0
    assert disks["/dev/sdb"]["media_type"] == "hdd"


def test_parse_bmh_hardware_nics_have_no_pci_or_numa():
    """The module's own documented limitation of this data source --
    confirms it's actually None, not silently defaulted to something
    that looks plausible but isn't real."""
    result = parse_bmh_hardware(REALISTIC_BMH_HARDWARE)
    for nic in result["nics"]:
        assert nic["pci_address"] is None
        assert nic["numa_node"] is None


def test_parse_bmh_hardware_handles_completely_empty_input():
    """Ironic inspection can report an essentially-empty hardware dict
    before it's actually finished -- must not crash."""
    result = parse_bmh_hardware({})
    assert result["cpu_cores_per_socket"] == 0
    assert result["memory_gb"] == 0
    assert result["nics"] == []
    assert result["disks"] == []


def test_enrich_uses_richer_socket_count_when_ipa_reports_it():
    base = parse_bmh_hardware(REALISTIC_BMH_HARDWARE)  # cpu_sockets=1 (conservative guess)
    result = enrich_with_ironic_inventory(base, REALISTIC_IPA_INVENTORY)
    assert result["cpu_sockets"] == 2  # corrected by the richer IPA data
    assert result["cpu_cores_per_socket"] == 16  # 64 logical / (2 sockets * 2 threads)


def test_enrich_adds_pci_and_numa_from_ipa_interfaces():
    base = parse_bmh_hardware(REALISTIC_BMH_HARDWARE)
    result = enrich_with_ironic_inventory(base, REALISTIC_IPA_INVENTORY)
    nic = result["nics"][0]
    assert nic["pci_address"] == "0000:37:00.0"
    assert nic["numa_node"] == 0
    assert nic["sriov_capable"] is True
    assert nic["total_vfs"] == 8
    assert nic["speed_gbps"] == 100.0


def test_enrich_disk_nvme_detection_from_device_name():
    base = parse_bmh_hardware(REALISTIC_BMH_HARDWARE)
    result = enrich_with_ironic_inventory(base, REALISTIC_IPA_INVENTORY)
    disk = result["disks"][0]
    assert disk["media_type"] == "nvme"
    assert disk["size_gb"] == 3200.0


def test_threads_per_core_zero_does_not_crash():
    """The actual bug this test file's development found: if
    cpu_threads_per_core is ever 0 in the stored asset (nothing
    previously stopped this at the API layer either -- now fixed in
    HardwareAssetCreate's schema, see tests/test_hardware_assets_api.py),
    and the fresh Ironic inventory doesn't report an 'ht' CPU flag, the
    old code divided total_logical // (socket_count * 0), a bare
    ZeroDivisionError raised straight out of a real user-facing endpoint
    (POST /hardware-assets/{id}/sync-from-ironic). Must degrade to a
    safe 0 instead of crashing."""
    base = {"cpu_sockets": 1, "cpu_cores_per_socket": 0, "cpu_threads_per_core": 0, "memory_gb": 0}
    inventory = {"cpu": {"count": 64, "flags": []}}  # no "ht" flag present

    result = enrich_with_ironic_inventory(base, inventory)  # must not raise

    assert result["cpu_cores_per_socket"] == 0


def test_socket_count_zero_does_not_crash():
    """Same defensive-guard class of bug, the other operand: a
    malformed/zero socket_count must also degrade safely rather than
    dividing by zero."""
    base = {"cpu_sockets": 0, "cpu_cores_per_socket": 0, "cpu_threads_per_core": 2, "memory_gb": 0}
    inventory = {"cpu": {"count": 64, "socket_count": 0, "flags": []}}

    result = enrich_with_ironic_inventory(base, inventory)  # must not raise

    assert result["cpu_cores_per_socket"] == 0


def test_enrich_preserves_base_fields_not_present_in_inventory():
    base = {
        "cpu_sockets": 1,
        "cpu_cores_per_socket": 16,
        "cpu_threads_per_core": 2,
        "memory_gb": 64,
        "vendor": "Dell Inc.",
        "serial_number": "KEEP-ME",
    }
    result = enrich_with_ironic_inventory(base, {})  # empty inventory: nothing to enrich with
    assert result["vendor"] == "Dell Inc."
    assert result["serial_number"] == "KEEP-ME"


def test_enrich_empty_inventory_does_not_crash_and_falls_back_to_base():
    base = {"cpu_sockets": 2, "cpu_cores_per_socket": 32, "cpu_threads_per_core": 2, "memory_gb": 256}
    result = enrich_with_ironic_inventory(base, {})
    assert result["cpu_sockets"] == 2
    assert result["cpu_cores_per_socket"] == 32
    assert result["memory_gb"] == 256
