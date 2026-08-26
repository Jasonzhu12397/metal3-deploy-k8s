"""
Cluster API (CAPI) orchestration for the *target* production cluster.

This drives cluster.x-k8s.io + infrastructure.cluster.x-k8s.io (Metal3)
custom resources from the management cluster (the ephemeral PXE node
during bootstrap, or a permanent management cluster afterwards), matching
the CAPI + Metal3 flow implied by the uploaded ccdadm-style config
(control-plane pool, worker_pools, networks, addons).
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.core.config import get_settings
from app.services.kubernetes import KubernetesService
from app.services.yaml_generator import YamlGeneratorService

logger = logging.getLogger(__name__)
settings = get_settings()

CAPI_GROUP = "cluster.x-k8s.io"
CAPI_VERSION = "v1beta1"
INFRA_GROUP = "infrastructure.cluster.x-k8s.io"
INFRA_VERSION = "v1beta1"
CP_GROUP = "controlplane.cluster.x-k8s.io"
CP_VERSION = "v1beta1"


class CAPIService:
    def __init__(
        self,
        k8s: Optional[KubernetesService] = None,
        yaml_gen: Optional[YamlGeneratorService] = None,
    ) -> None:
        self.k8s = k8s or KubernetesService()
        self.yaml_gen = yaml_gen or YamlGeneratorService()

    def render_manifests(self, cluster_spec: dict[str, Any]) -> list[dict[str, Any]]:
        """Renders Cluster / <Provider>Cluster / KubeadmControlPlane /
        <Provider>MachineTemplate / MachineDeployment objects from the
        cluster spec and returns them as parsed dicts, ready to apply.
        Which concrete provider Kinds come out is entirely decided by
        cluster_spec["infrastructure_provider"] inside
        YamlGeneratorService.render_cluster_config -- this method and
        apply_cluster() below don't need to know or care which provider
        it is, since _plural_for()'s naive lowercase-plus-s fallback
        already covers Metal3/OpenStack/vSphere/KubeVirt's actual CRD
        plurals correctly."""
        rendered_yaml = self.yaml_gen.render_cluster_config(cluster_spec)
        return self.yaml_gen.parse_multi(rendered_yaml)

    def apply_cluster(self, cluster_spec: dict[str, Any], namespace: str) -> list[dict[str, Any]]:
        manifests = self.render_manifests(cluster_spec)
        results = []
        for manifest in manifests:
            group, version = self._group_version_for(manifest["apiVersion"])
            plural = self._plural_for(manifest["kind"])
            manifest.setdefault("metadata", {}).setdefault("namespace", namespace)
            results.append(
                self.k8s.apply_custom_object(group, version, namespace, plural, manifest)
            )
            logger.info(
                "Applied %s/%s %s", manifest["kind"], manifest["metadata"]["name"], namespace
            )
        return results

    def get_cluster_status(self, name: str, namespace: str) -> Optional[dict[str, Any]]:
        obj = self.k8s.get_custom_object(CAPI_GROUP, CAPI_VERSION, namespace, "clusters", name)
        return obj.get("status") if obj else None

    def delete_cluster(self, name: str, namespace: str) -> None:
        self.k8s.delete_custom_object(CAPI_GROUP, CAPI_VERSION, namespace, "clusters", name)

    def list_machines(self, cluster_name: str, namespace: str) -> list[dict[str, Any]]:
        selector = f"cluster.x-k8s.io/cluster-name={cluster_name}"
        return self.k8s.list_custom_objects(
            CAPI_GROUP, CAPI_VERSION, namespace, "machines", label_selector=selector
        )

    # ---- helpers -------------------------------------------------
    @staticmethod
    def _group_version_for(api_version: str) -> tuple[str, str]:
        if "/" in api_version:
            group, version = api_version.split("/", 1)
            return group, version
        return "", api_version

    @staticmethod
    def _plural_for(kind: str) -> str:
        # naive pluralisation good enough for the small set of CAPI/Metal3
        # kinds this service manages -- extend as needed.
        overrides = {
            "Cluster": "clusters",
            "Metal3Cluster": "metal3clusters",
            "KubeadmControlPlane": "kubeadmcontrolplanes",
            "Metal3MachineTemplate": "metal3machinetemplates",
            "MachineDeployment": "machinedeployments",
            "KubeadmConfigTemplate": "kubeadmconfigtemplates",
            "Metal3Machine": "metal3machines",
        }
        return overrides.get(kind, kind.lower() + "s")
