"""
BMC credential + power-management service.

This service's own job is narrow: write credentials straight into a
Kubernetes Secret (referenced by BareMetalHost.spec.bmc.credentialsName)
and nothing else -- it never touches this app's database or writes
credentials to disk/logs itself.

Separately, callers (api/baremetalhosts.py, api/hardware_assets.py) DO
persist an encrypted copy of the password in this app's own database via
services/crypto.py, so a deleted/rotated Secret can be recreated without
asking anyone to re-type it. That's a deliberate, distinct decision made
at the API layer, not something this service does on its own -- keeping
BMCService itself free of DB access means the "write the Secret" and
"remember it for later, encrypted" concerns stay independently testable
and one can't silently start depending on the other.
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
