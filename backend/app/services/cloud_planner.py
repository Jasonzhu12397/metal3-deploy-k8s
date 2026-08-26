"""
The non-metal3 counterpart to AssetPlannerService: builds the cluster_spec
that renders into Cluster/*Cluster/*MachineTemplate manifests for a
cloud/VM-backed target cluster (OpenStack, vSphere, KubeVirt), straight
from what was declared at cluster-creation time -- flavor/image per pool,
no physical HardwareAsset to pick, no CPU-reservation math, no BMH to wait
on. Kept deliberately separate from AssetPlannerService rather than
unifying them: the two providers' inputs don't actually overlap (PCI
addresses and reserved-cpu strings vs. flavor names and image references),
and forcing them through one interface would just mean a lot of "N/A for
this provider" fields.
"""
from __future__ import annotations

from typing import Any

from app.models.cluster import Cluster
from app.services.yaml_generator import PROVIDER_CONFIG_KEYS, YamlGeneratorService


class CloudPlannerService:
    def __init__(self, yaml_gen: YamlGeneratorService | None = None) -> None:
        self.yaml_gen = yaml_gen or YamlGeneratorService()

    def build_cluster_spec(self, cluster: Cluster) -> dict[str, Any]:
        provider = cluster.infrastructure_provider.value if hasattr(
            cluster.infrastructure_provider, "value"
        ) else cluster.infrastructure_provider

        spec: dict[str, Any] = {
            "name": cluster.name,
            "namespace": cluster.namespace,
            "infrastructure_provider": provider,
            "control_plane_count": cluster.control_plane_count,
            "control_plane_endpoint": cluster.control_plane_endpoint,
            "worker_pools": cluster.worker_pool_config.get("pools", []),
            **cluster.spec,
            # No physical hosts for a cloud provider -- the deployment task
            # skips APPLYING_BMH/WAITING_FOR_HOSTS entirely when this list
            # is empty (see tasks/deployment_tasks.py).
            "hosts": [],
        }

        # Guarantee the provider's own config sub-dict exists (even empty)
        # -- see yaml_generator.PROVIDER_CONFIG_KEYS for why this matters
        # under StrictUndefined.
        config_key = PROVIDER_CONFIG_KEYS.get(provider)
        if config_key:
            spec.setdefault(config_key, {})

        return spec

    def generate_cluster_config_yaml(self, cluster: Cluster) -> str:
        cluster_spec = self.build_cluster_spec(cluster)
        return self.yaml_gen.render_cluster_config(cluster_spec)
