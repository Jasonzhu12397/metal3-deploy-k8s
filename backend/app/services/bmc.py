"""
BMC credential + power-management service.

Credentials are written straight into a Kubernetes Secret (referenced by
BareMetalHost.spec.bmc.credentialsName) and are never persisted to the
application database or written to disk/logs by this service.
"""
from __future__ import annotations

import logging

from app.core.config import get_settings
from app.schemas.baremetalhost import BMCCredentials
from app.services.kubernetes import KubernetesService

logger = logging.getLogger(__name__)
settings = get_settings()


class BMCService:
    def __init__(self, k8s: KubernetesService | None = None) -> None:
        self.k8s = k8s or KubernetesService()

    def secret_name_for_host(self, host_name: str) -> str:
        return f"{host_name}-bmc-secret"

    def store_credentials(
        self, host_name: str, creds: BMCCredentials, namespace: str | None = None
    ) -> str:
        namespace = namespace or settings.CAPI_NAMESPACE
        secret_name = self.secret_name_for_host(host_name)
        self.k8s.create_or_update_secret(
            name=secret_name,
            namespace=namespace,
            string_data={"username": creds.username, "password": creds.password},
        )
        logger.info("Stored BMC credentials for %s as secret %s", host_name, secret_name)
        return secret_name

    # Power actions are delegated to Metal3/BMH controllers by flipping
    # BareMetalHost.spec.online -- see Metal3Service.set_power_state. A
    # direct-to-BMC path (e.g. redfish/netconf) can be added here if the
    # deployment needs it independent of Metal3.
