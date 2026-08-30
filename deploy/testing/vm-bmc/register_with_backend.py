#!/usr/bin/env python3
"""
Takes the test_nodes.json produced by create_test_nodes.py and registers
each virtual node as a real BareMetalHost through this project's actual
API -- POST /api/v1/auth/login, then POST /api/v1/baremetalhosts per
node, exactly the same calls a human would make (or the frontend does).
This is the piece that makes the exercise "test the whole project", not
just "I have some VMs now": from here on, Ironic/baremetal-operator on
your management cluster take over exactly as they would for a real
physical server.

Unlike create_test_nodes.py, THIS script's HTTP-calling logic has been
tested against a real (locally-mocked-K8s) instance of the backend --
see tests/test_dev_vm_bmc_registration.py in the project root. What
hasn't been tested here is the actual libvirt/sushy-tools side, since
this sandbox has neither.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests


def login(api_base: str, username: str, password: str) -> str:
    resp = requests.post(f"{api_base}/api/v1/auth/login", json={"username": username, "password": password})
    resp.raise_for_status()
    return resp.json()["access_token"]


def register_node(
    api_base: str,
    token: str,
    node: dict,
    sushy_host: str,
    sushy_port: int,
    node_pool_name: str,
    bmc_username: str,
    bmc_password: str,
) -> None:
    bmc_address = f"redfish://{sushy_host}:{sushy_port}/redfish/v1/Systems/{node['libvirt_uuid']}"
    payload = {
        "name": node["name"],
        "node_pool_name": node_pool_name,
        "bmc_address": bmc_address,
        "boot_mac_address": node["boot_mac_address"],
        "credentials": {"username": bmc_username, "password": bmc_password},
        "online": False,
        # sushy-emulator isn't presenting a real TLS cert in this setup
        # (see sushy-emulator.conf) -- irrelevant anyway since bmc_address
        # uses redfish:// not redfish+https://, but set explicitly so
        # it's not accidentally load-bearing if you switch this test rig
        # to TLS later.
        "disable_certificate_verification": True,
    }
    resp = requests.post(
        f"{api_base}/api/v1/baremetalhosts",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    if resp.status_code >= 300:
        print(f"  FAILED ({resp.status_code}): {node['name']}: {resp.text}", file=sys.stderr)
        return
    print(f"  registered {node['name']} -> {bmc_address}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--nodes-file", default="test_nodes.json")
    parser.add_argument("--api-base", default="http://localhost:8000", help="this backend's base URL")
    parser.add_argument("--admin-username", default="admin", help="this backend's login, not the BMC's")
    parser.add_argument("--admin-password", required=True, help="this backend's login, not the BMC's")
    parser.add_argument("--node-pool-name", default="test-pool")
    parser.add_argument("--sushy-host", default="127.0.0.1", help="where sushy-emulator is listening")
    parser.add_argument("--sushy-port", type=int, default=8000)
    parser.add_argument(
        "--bmc-username", default="admin", help="must match a user in sushy-emulator's htpasswd auth file"
    )
    parser.add_argument("--bmc-password", required=True, help="must match that same htpasswd entry")
    args = parser.parse_args()

    nodes = json.loads(Path(args.nodes_file).read_text())
    if not nodes:
        print("no nodes found in nodes file", file=sys.stderr)
        sys.exit(1)

    token = login(args.api_base, args.admin_username, args.admin_password)
    print(f"logged in to {args.api_base} as {args.admin_username}", file=sys.stderr)

    for node in nodes:
        register_node(
            args.api_base,
            token,
            node,
            args.sushy_host,
            args.sushy_port,
            args.node_pool_name,
            args.bmc_username,
            args.bmc_password,
        )


if __name__ == "__main__":
    main()
