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
        tmpl = self.env.get_template("capi/cluster-template.yaml.j2")
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
