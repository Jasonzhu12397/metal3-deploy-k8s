from __future__ import annotations

import uuid
from typing import Optional

from pydantic import BaseModel

from app.models.deployment import DeploymentPhase


class DeploymentCreate(BaseModel):
    cluster_id: uuid.UUID
    # If true, also (re)generates bmh.yaml / k8s-config.yaml / eph-net.yaml
    # from the cluster spec before applying anything.
    regenerate_manifests: bool = True


class DeploymentRead(BaseModel):
    id: uuid.UUID
    cluster_id: uuid.UUID
    phase: DeploymentPhase
    celery_task_id: Optional[str] = None
    error_message: Optional[str] = None
    log: Optional[str] = None

    class Config:
        from_attributes = True
