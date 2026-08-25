from __future__ import annotations

import re
import uuid
from typing import Optional

from pydantic import BaseModel, field_validator

from app.models.baremetalhost import BMHState

MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")


class BMCCredentials(BaseModel):
    """Credentials are only ever accepted transiently by the API and are
    immediately written into a Kubernetes Secret; they are never persisted
    in the application database or logged."""

    username: str
    password: str


class BareMetalHostCreate(BaseModel):
    name: str
    node_pool_name: str
    bmc_address: str  # e.g. sdi+netconf://172.18.37.1/<vpod>/<node-id>
    boot_mac_address: str
    credentials: BMCCredentials
    online: bool = False
    disable_certificate_verification: bool = True
    root_device_hint_model: Optional[str] = None

    @field_validator("boot_mac_address")
    @classmethod
    def validate_mac(cls, v: str) -> str:
        if not MAC_RE.match(v):
            raise ValueError("boot_mac_address must look like aa:bb:cc:dd:ee:ff")
        return v.lower()


class BareMetalHostRead(BaseModel):
    id: uuid.UUID
    name: str
    node_pool_name: str
    bmc_address: str
    boot_mac_address: str
    online: bool
    state: BMHState
    cluster_id: Optional[uuid.UUID] = None

    class Config:
        from_attributes = True


class BareMetalHostBulkImport(BaseModel):
    """Accepts a parsed bmhosts.yaml-style document (a list of BMH specs) so
    the whole fleet can be registered in one call instead of one-by-one."""

    hosts: list[BareMetalHostCreate]
