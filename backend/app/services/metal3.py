"""
Metal3 BareMetalHost (BMH) lifecycle management.

Talks to the management cluster's Metal3 CRDs (metal3.io/v1alpha1). The
"eph-node" (ephemeral, PXE-booted, in-memory bootstrap node) is itself
usually represented as a BareMetalHost with an annotation such as
`baremetalhost.metal3.io/paused: ccd-ephemeral`, matching the pattern
already present in the uploaded bmhosts.yaml.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.core.config import get_settings
from app.schemas.baremetalhost import BareMetalHostCreate
from app.services.bmc import BMCService
from app.services.kubernetes import KubernetesService
from app.services.yaml_generator import YamlGeneratorService

logger = logging.getLogger(__name__)
settings = get_settings()

GROUP = "metal3.io"
VERSION = "v1alpha1"
PLURAL = "baremetalhosts"


class Metal3Service:
    def __init__(
        self,
        k8s: Optional[KubernetesService] = None,
        bmc: Optional[BMCService] = None,
        yaml_gen: Optional[YamlGeneratorService] = None,
    ) -> None:
        self.k8s = k8s or KubernetesService()
        self.bmc = bmc or BMCService(self.k8s)
        self.yaml_gen = yaml_gen or YamlGeneratorService()

    def register_host(self, spec: BareMetalHostCreate, namespace: str | None = None) -> dict[str, Any]:
        namespace = namespace or settings.CAPI_NAMESPACE
        secret_ref = self.bmc.store_credentials(spec.name, spec.credentials, namespace)

        manifest = {
            "apiVersion": f"{GROUP}/{VERSION}",
            "kind": "BareMetalHost",
            "metadata": {
                "name": spec.name,
                "namespace": namespace,
                "labels": {
                    "nodeType": "worker",
                    "node-pool-name": spec.node_pool_name,
                },
            },
            "spec": {
                "bmc": {
                    "address": spec.bmc_address,
                    "credentialsName": secret_ref,
                    "disableCertificateVerification": spec.disable_certificate_verification,
                },
                "bootMACAddress": spec.boot_mac_address,
                "online": spec.online,
            },
        }
        if spec.root_device_hint_model:
            manifest["spec"]["rootDeviceHints"] = {"model": spec.root_device_hint_model}

        result = self.k8s.apply_custom_object(GROUP, VERSION, namespace, PLURAL, manifest)
        logger.info("Applied BareMetalHost %s/%s", namespace, spec.name)
        return result

    def bulk_register(
        self, hosts: list[BareMetalHostCreate], namespace: str | None = None
    ) -> list[dict[str, Any]]:
        return [self.register_host(h, namespace) for h in hosts]

    def get_host_status(self, name: str, namespace: str | None = None) -> Optional[dict[str, Any]]:
        namespace = namespace or settings.CAPI_NAMESPACE
        obj = self.k8s.get_custom_object(GROUP, VERSION, namespace, PLURAL, name)
        if not obj:
            return None
        return obj.get("status", {})

    def get_hardware_details(self, name: str, namespace: str | None = None) -> Optional[dict[str, Any]]:
        """Returns BMH.status.hardware -- the Ironic-inspected CPU/RAM/NIC/
        disk data baremetal-operator surfaces once introspection completes.
        None if the BMH doesn't exist yet or hasn't been inspected."""
        status = self.get_host_status(name, namespace) or {}
        return status.get("hardware")

    def set_power_state(self, name: str, online: bool, namespace: str | None = None) -> None:
        """Flips spec.online -- Metal3's baremetal-operator reconciles the
        actual BMC power state to match."""
        namespace = namespace or settings.CAPI_NAMESPACE
        obj = self.k8s.get_custom_object(GROUP, VERSION, namespace, PLURAL, name)
        if not obj:
            raise ValueError(f"BareMetalHost {namespace}/{name} not found")
        obj["spec"]["online"] = online
        self.k8s.apply_custom_object(GROUP, VERSION, namespace, PLURAL, obj)

    def list_hosts(self, namespace: str | None = None, node_pool: str | None = None) -> list[dict[str, Any]]:
        namespace = namespace or settings.CAPI_NAMESPACE
        selector = f"node-pool-name={node_pool}" if node_pool else ""
        return self.k8s.list_custom_objects(GROUP, VERSION, namespace, PLURAL, selector)

    def import_from_bmhosts_yaml(
        self, yaml_text: str, credentials_by_host: dict[str, Any], namespace: str | None = None
    ) -> list[dict[str, Any]]:
        """Parses a bmhosts.yaml-style multi-document file (BareMetalHost +
        Secret docs, as in the uploaded example) and re-applies each BMH
        against the *provided* credentials map rather than any Secret data
        embedded in the file, so stale/plaintext secrets in the file are
        never reused verbatim."""
        docs = self.yaml_gen.parse_multi(yaml_text)
        applied = []
        for doc in docs:
            if doc.get("kind") != "BareMetalHost":
                continue
            name = doc["metadata"]["name"]
            creds = credentials_by_host.get(name)
            if not creds:
                logger.warning("No credentials supplied for host %s, skipping", name)
                continue
            spec = BareMetalHostCreate(
                name=name,
                node_pool_name=doc["metadata"]["labels"].get("node-pool-name", "default"),
                bmc_address=doc["spec"]["bmc"]["address"],
                boot_mac_address=doc["spec"]["bootMACAddress"],
                credentials=creds,
                online=doc["spec"].get("online", False),
                disable_certificate_verification=doc["spec"]["bmc"].get(
                    "disableCertificateVerification", True
                ),
            )
            applied.append(self.register_host(spec, namespace))
        return applied
