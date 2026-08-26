"""
Renders the three artefacts the user already hand-maintains today:

  * bmh.yaml       -> one BareMetalHost + Secret per physical node
  * k8s-config.yaml -> ccdadm/CAPI-style cluster spec (infra/kubernetes/addons)
  * eph-net.yaml    -> network config for the ephemeral (PXE, in-memory) node
                       used to bootstrap the target cluster via Cluster API

Templates live in /templates and are plain Jinja2 -- edit them there rather
than hard-coding YAML in Python. This module never receives raw secret
material directly; callers pass a `secret_ref` (the name of a Kubernetes
Secret already created via BMCService) instead of a password.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from app.core.config import get_settings

settings = get_settings()

# Which Jinja template renders a target cluster's Cluster API manifests,
# keyed by Cluster.infrastructure_provider. Adding a new provider means
# adding one template file + one line here -- see
# templates/capi/providers/*.yaml.j2 for the CAPO/CAPV/CAPK ones.
PROVIDER_TEMPLATES = {
    "metal3": "capi/cluster-template.yaml.j2",
    "openstack": "capi/providers/openstack.yaml.j2",
    "vsphere": "capi/providers/vsphere.yaml.j2",
    "kubevirt": "capi/providers/kubevirt.yaml.j2",
}

# Every cloud provider template dot-accesses its own config sub-dict
# (cluster.openstack.*, cluster.vsphere.*, cluster.kubevirt.*) with
# `| default(...)` at the *leaf* level -- but under Jinja's StrictUndefined
# (which this module uses everywhere else to catch real typos), even
# looking up a *missing top-level key* like `cluster.openstack` raises
# immediately, before any leaf `| default(...)` gets a chance to run. So
# the sub-dict itself has to exist (even empty) before rendering, or every
# provider's own optional fields would crash the whole render. See
# CloudPlannerService.build_cluster_spec, which guarantees this.
PROVIDER_CONFIG_KEYS = {
    "openstack": "openstack",
    "vsphere": "vsphere",
    "kubevirt": "kubevirt",
}


def _env() -> Environment:
    templates_dir = Path(__file__).resolve().parents[3] / "templates"
    if not templates_dir.exists():
        # fall back to configured path (e.g. when packaged differently)
        templates_dir = Path(settings.TEMPLATES_DIR)
    return Environment(
        loader=FileSystemLoader(str(templates_dir)),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )


class YamlGeneratorService:
    def __init__(self) -> None:
        self.env = _env()

    # ---- bmh.yaml -------------------------------------------------
    def render_bmh(self, hosts: list[dict[str, Any]]) -> str:
        """hosts: list of dicts with name, node_pool_name, bmc_address,
        boot_mac_address, secret_ref (NOT a raw password), online, etc."""
        tmpl = self.env.get_template("bmh/bmh-template.yaml.j2")
        return tmpl.render(hosts=hosts)

    # ---- k8s-config.yaml -------------------------------------------
    def render_cluster_config(self, cluster_spec: dict[str, Any]) -> str:
        provider = cluster_spec.get("infrastructure_provider", "metal3")
        template_path = PROVIDER_TEMPLATES.get(provider)
        if template_path is None:
            raise ValueError(
                f"unknown infrastructure_provider '{provider}' -- expected one of "
                f"{sorted(PROVIDER_TEMPLATES)}"
            )
        tmpl = self.env.get_template(template_path)
        return tmpl.render(cluster=cluster_spec)

    def render_metal3_config(self, metal3_spec: dict[str, Any]) -> str:
        tmpl = self.env.get_template("metal3/metal3-config.yaml.j2")
        return tmpl.render(metal3=metal3_spec)

    # ---- eph-net.yaml ------------------------------------------------
    def render_ephemeral_network(self, net_spec: dict[str, Any]) -> str:
        tmpl = self.env.get_template("network/eph-net-template.yaml.j2")
        return tmpl.render(net=net_spec)

    # ---- helpers -------------------------------------------------
    @staticmethod
    def write(content: str, out_path: str) -> str:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w") as f:
            f.write(content)
        return out_path

    @staticmethod
    def parse(content: str) -> Any:
        return yaml.safe_load(content)

    @staticmethod
    def parse_multi(content: str) -> list[Any]:
        return [d for d in yaml.safe_load_all(content) if d is not None]
