#!/usr/bin/env python3
"""
Generates sushy-fake.conf (N fake Redfish "systems" for sushy-emulator's
--fake driver) and test_nodes.json (the same format
register_with_backend.py already reads) -- no libvirt/KVM needed at all,
unlike deploy/testing/vm-bmc/. This is the right starting point if you
don't have (or can't get) nested virtualization on your host: it proves
out the exact same BareMetalHost registration -> Ironic inspection ->
provisioning flow using one lightweight container.

The tradeoff for not needing real virtualization: a fake system's
"provisioning" isn't backed by anything that can actually boot an OS --
Ironic can power it on/off and flip its boot-device flag, and this is
genuinely enough to validate the registration/inspection state machine,
but if you need to see an actual OS actually get installed end to end,
you need deploy/testing/vm-bmc/ (real VMs) or real hardware eventually.
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path


def random_locally_administered_mac(index: int) -> str:
    # 52:54:00 is the same QEMU/libvirt-reserved OUI used in vm-bmc/'s
    # generator -- kept consistent so both testing paths produce
    # obviously-fake, never-colliding-with-real-hardware MACs.
    return f"52:54:00:00:00:{index:02x}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--count", type=int, default=3)
    parser.add_argument("--name-prefix", default="fake-bmc-node")
    parser.add_argument("--conf-out", default="sushy-fake.conf")
    parser.add_argument("--nodes-out", default="test_nodes.json")
    parser.add_argument(
        "--listen-port",
        type=int,
        default=8000,
        help="port sushy-emulator listens on INSIDE its container (matches the Dockerfile's EXPOSE 8000 -- "
        "leave this at the default unless you also change the Dockerfile; this is not the host-mapped "
        "port register_with_backend.py's --sushy-port needs, which is whatever docker-compose.yml maps "
        "it to externally, e.g. 8001)",
    )
    args = parser.parse_args()

    systems = []
    nodes = []
    for i in range(1, args.count + 1):
        uuid = f"{i:08x}-0000-0000-0000-000000000000"
        name = f"{args.name_prefix}-{i:02d}"
        mac = random_locally_administered_mac(i)
        systems.append(
            {
                "uuid": uuid,
                "name": name,
                "power_state": "Off",
                "nics": [{"mac": mac, "ip": f"192.0.2.{10 + i}"}],
            }
        )
        # Same shape create_test_nodes.py (the libvirt path) produces --
        # register_with_backend.py doesn't care which generator made this.
        nodes.append({"name": name, "redfish_uuid": uuid, "boot_mac_address": mac})

    conf_lines = [
        "SUSHY_EMULATOR_LISTEN_IP = '0.0.0.0'",
        f"SUSHY_EMULATOR_LISTEN_PORT = {args.listen_port}",
        f"SUSHY_EMULATOR_FAKE_SYSTEMS = {json.dumps(systems, indent=4)}",
    ]
    Path(args.conf_out).write_text("\n".join(conf_lines) + "\n")
    Path(args.nodes_out).write_text(json.dumps(nodes, indent=2))

    print(f"Wrote {args.conf_out} ({args.count} fake systems) and {args.nodes_out}")
    print("Next: docker compose up -d --build   (see docker-compose.yml in this directory)")
    print("Then: python3 register_with_backend.py --admin-password ... --bmc-password admin:password (see README.md)")


if __name__ == "__main__":
    main()
