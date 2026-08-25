"""
Thin wrapper around the official `kubernetes` python client, scoped to the
*management* cluster (the ephemeral/bootstrap node or a permanent CAPI
management cluster) where Metal3 + Cluster API run.

Auth: loads a kubeconfig from settings.MGMT_KUBECONFIG_PATH, or falls back
to in-cluster config when running as a pod. Never embed kubeconfig
contents or tokens in code/config files -- mount them as a Secret/volume.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from kubernetes import client, config
from kubernetes.client.rest import ApiException
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class KubernetesService:
    def __init__(self) -> None:
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        try:
            if settings.MGMT_KUBECONFIG_PATH:
                config.load_kube_config(config_file=settings.MGMT_KUBECONFIG_PATH)
            else:
                config.load_incluster_config()
        except Exception:
            logger.warning("Falling back to default kubeconfig location (~/.kube/config)")
            config.load_kube_config()
        self._loaded = True

    @property
    def core_v1(self) -> client.CoreV1Api:
        self._ensure_loaded()
        return client.CoreV1Api()

    @property
    def custom_objects(self) -> client.CustomObjectsApi:
        self._ensure_loaded()
        return client.CustomObjectsApi()

    # ---- generic Secret helpers -----------------------------------
    def create_or_update_secret(
        self, name: str, namespace: str, string_data: dict[str, str], secret_type: str = "Opaque"
    ) -> None:
        body = client.V1Secret(
            metadata=client.V1ObjectMeta(name=name, namespace=namespace),
            string_data=string_data,
            type=secret_type,
        )
        try:
            self.core_v1.create_namespaced_secret(namespace=namespace, body=body)
            logger.info("Created secret %s/%s", namespace, name)
        except ApiException as exc:
            if exc.status == 409:
                self.core_v1.replace_namespaced_secret(name=name, namespace=namespace, body=body)
                logger.info("Updated secret %s/%s", namespace, name)
            else:
                raise

    # ---- generic Custom Resource helpers (BMH, Cluster, Machine...) --
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    def apply_custom_object(
        self, group: str, version: str, namespace: str, plural: str, manifest: dict[str, Any]
    ) -> dict[str, Any]:
        name = manifest["metadata"]["name"]
        api = self.custom_objects
        try:
            return api.create_namespaced_custom_object(
                group=group, version=version, namespace=namespace, plural=plural, body=manifest
            )
        except ApiException as exc:
            if exc.status == 409:
                existing = api.get_namespaced_custom_object(
                    group=group, version=version, namespace=namespace, plural=plural, name=name
                )
                manifest["metadata"]["resourceVersion"] = existing["metadata"]["resourceVersion"]
                return api.replace_namespaced_custom_object(
                    group=group,
                    version=version,
                    namespace=namespace,
                    plural=plural,
                    name=name,
                    body=manifest,
                )
            raise

    def get_custom_object(
        self, group: str, version: str, namespace: str, plural: str, name: str
    ) -> Optional[dict[str, Any]]:
        try:
            return self.custom_objects.get_namespaced_custom_object(
                group=group, version=version, namespace=namespace, plural=plural, name=name
            )
        except ApiException as exc:
            if exc.status == 404:
                return None
            raise

    def list_custom_objects(
        self, group: str, version: str, namespace: str, plural: str, label_selector: str = ""
    ) -> list[dict[str, Any]]:
        resp = self.custom_objects.list_namespaced_custom_object(
            group=group,
            version=version,
            namespace=namespace,
            plural=plural,
            label_selector=label_selector,
        )
        return resp.get("items", [])

    def delete_custom_object(
        self, group: str, version: str, namespace: str, plural: str, name: str
    ) -> None:
        try:
            self.custom_objects.delete_namespaced_custom_object(
                group=group, version=version, namespace=namespace, plural=plural, name=name
            )
        except ApiException as exc:
            if exc.status != 404:
                raise
