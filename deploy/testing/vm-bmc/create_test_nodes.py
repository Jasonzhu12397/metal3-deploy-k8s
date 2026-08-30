#!/usr/bin/env python3
"""
Creates N libvirt VMs as stand-ins for physical bare-metal nodes -- no
OS installed, left powered off, ready for Ironic to PXE-boot and
provision through sushy-tools' virtual Redfish BMC (see
sushy-emulator.conf and register_with_backend.py in this directory).

This mirrors what metal3-io's own CI (the metal3-dev-env project) does
to test the BareMetalHost lifecycle without real hardware -- this script
doesn't invent a new approach, it automates the same one, scoped to this
project's registration API.

WARNING: this was written and syntax-checked in an environment with no
libvirt/KVM available at all (a sandboxed container) -- it has NOT been
run against a real libvirtd. Read it before trusting it, and expect to
debug the first run on your actual Linux host.

Requires (on the Linux host actually running this -- not a container
without KVM access):
  - libvirt + KVM: /dev/kvm must exist. On a Hyper-V VM, this needs
    nested virtualization enabled from the Windows host FIRST:
      Set-VMProcessor -VMName <name> -ExposeVirtualizationExtensions $true
    (VM must be powered off when you run that, from an elevated
    PowerShell on the Windows 11 host -- not inside the Linux VM.)
  - virtinst (provides the `virt-install` CLI this script shells out to)
  - A libvirt network for the VMs' boot NIC to attach to, already
    configured to hand out DHCP/PXE from wherever your Ironic
    provisioning network lives (or reuse an existing bridge if your
    management cluster's DHCP/PXE already serves this subnet).
"""
from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path


def run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd)}\n{result.stderr}")
    return result.stdout


def random_libvirt_mac() -> str:
    # 52:54:00:xx:xx:xx is QEMU/libvirt's assigned OUI prefix for exactly
    # this purpose (locally-administered, avoids colliding with anything
    # real) -- the same range `virt-install` itself would pick from.
    tail = [random.randint(0x00, 0xFF) for _ in range(3)]
    return "52:54:00:" + ":".join(f"{b:02x}" for b in tail)


def define_vm(name: str, ram_mb: int, vcpus: int, disk_gb: int, network: str, pool: str, mac: str) -> None:
    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as tmp:
        xml_path = Path(tmp.name)

    # --print-xml generates the domain definition WITHOUT creating or
    # starting anything -- `virt-install` normally boots the VM
    # immediately, which we don't want (there's no OS/install media; the
    # whole point is that Ironic controls power-on later, exactly like a
    # real server sitting racked and powered off until it's provisioned).
    xml = run([
        "virt-install",
        "--name", name,
        "--ram", str(ram_mb),
        "--vcpus", str(vcpus),
        "--disk", f"size={disk_gb},pool={pool},format=qcow2",
        "--network", f"network={network},mac={mac}",
        "--boot", "network,hd",  # PXE first, local disk second (post-provisioning)
        "--os-variant", "generic",
        "--graphics", "none",
        "--noautoconsole",
        "--print-xml",
    ])
    xml_path.write_text(xml)

    run(["virsh", "define", str(xml_path)])
    xml_path.unlink(missing_ok=True)


def get_domain_uuid_and_mac(name: str) -> tuple[str, str]:
    dumped = run(["virsh", "dumpxml", name])
    root = ET.fromstring(dumped)
    uuid = root.findtext("uuid")
    mac_el = root.find(".//devices/interface/mac")
    mac = mac_el.get("address") if mac_el is not None else None
    if not uuid or not mac:
        raise RuntimeError(f"could not read back uuid/mac for domain {name} -- check `virsh dumpxml {name}`")
    return uuid, mac


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--count", type=int, default=1, help="how many virtual nodes to create")
    parser.add_argument("--name-prefix", default="metal3-test-node")
    parser.add_argument("--network", default="default", help="libvirt network name for the PXE/boot NIC")
    parser.add_argument("--pool", default="default", help="libvirt storage pool for the VM's disk")
    parser.add_argument("--ram-mb", type=int, default=4096)
    parser.add_argument("--vcpus", type=int, default=2)
    parser.add_argument("--disk-gb", type=int, default=20)
    parser.add_argument(
        "--out",
        default="test_nodes.json",
        help="where to write the created nodes' name/uuid/mac -- register_with_backend.py reads this",
    )
    args = parser.parse_args()

    nodes = []
    for i in range(args.count):
        name = f"{args.name_prefix}-{i + 1:02d}"
        mac = random_libvirt_mac()
        print(f"defining {name} (mac={mac})...", file=sys.stderr)
        define_vm(name, args.ram_mb, args.vcpus, args.disk_gb, args.network, args.pool, mac)
        uuid, confirmed_mac = get_domain_uuid_and_mac(name)
        nodes.append({"name": name, "libvirt_uuid": uuid, "boot_mac_address": confirmed_mac})
        print(f"  -> defined, libvirt uuid={uuid}", file=sys.stderr)

    Path(args.out).write_text(json.dumps(nodes, indent=2))
    print(f"\nWrote {len(nodes)} node(s) to {args.out}", file=sys.stderr)
    print("Next: start sushy-emulator (see README.md), then run register_with_backend.py", file=sys.stderr)


if __name__ == "__main__":
    main()
