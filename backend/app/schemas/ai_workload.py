from __future__ import annotations

import uuid
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.ai_workload import AIWorkloadStatus


class AIWorkloadCreate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    name: str
    cluster_id: uuid.UUID
    namespace: str = "default"
    model_id: str = Field(..., description='HuggingFace model reference, e.g. "Qwen/Qwen2.5-7B-Instruct"')
    gpu_count: int = Field(1, ge=1)
    replicas: int = Field(1, ge=1)
    image_tag: Optional[str] = None
    extra_args: list[str] = Field(default_factory=list)
    shm_size: Optional[str] = None
    # Name of an existing Secret (with a "token" key) on the TARGET
    # cluster, for gated HuggingFace models -- this app doesn't create
    # that Secret for you, since it'd mean handling yet another
    # credential type; create it yourself on the target cluster first
    # (kubectl create secret generic hf-token-secret --from-literal=token=...).
    hf_token_secret_name: Optional[str] = None


class AIWorkloadRead(BaseModel):
    model_config = ConfigDict(protected_namespaces=(), from_attributes=True)

    id: uuid.UUID
    name: str
    cluster_id: uuid.UUID
    namespace: str
    model_id: str
    gpu_count: int
    replicas: int
    status: AIWorkloadStatus
    error_message: Optional[str] = None
    service_endpoint: Optional[str] = None
