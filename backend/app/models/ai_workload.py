"""
A vLLM inference server deployed onto a *target* cluster (one this
project already provisioned via Cluster API) -- not a cluster addon
(see services/addon_catalog.py for those, which install onto the
cluster itself), this is a workload running on top of an already-running
cluster, the same way any Deployment+Service a user might apply by hand
would be.
"""
from __future__ import annotations

import enum
import uuid

from sqlalchemy import Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedModel


class AIWorkloadStatus(str, enum.Enum):
    PENDING = "pending"  # created in our DB, not yet applied to the target cluster
    DEPLOYING = "deploying"
    RUNNING = "running"
    FAILED = "failed"
    DELETED = "deleted"


class AIWorkload(TimestampedModel):
    __tablename__ = "ai_workloads"

    name: Mapped[str] = mapped_column(String(253), unique=True, index=True)
    cluster_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clusters.id"))
    namespace: Mapped[str] = mapped_column(String(253), default="default")

    # A HuggingFace model reference (e.g. "Qwen/Qwen2.5-7B-Instruct") --
    # vLLM downloads it itself on first start unless a PVC/volume with a
    # pre-cached copy is wired up separately; that caching setup is
    # environment-specific and out of scope here, same reasoning as why
    # this project doesn't automate the ephemeral node's own PXE boot.
    model_id: Mapped[str] = mapped_column(String(255))
    gpu_count: Mapped[int] = mapped_column(Integer, default=1)
    replicas: Mapped[int] = mapped_column(Integer, default=1)

    status: Mapped[AIWorkloadStatus] = mapped_column(Enum(AIWorkloadStatus), default=AIWorkloadStatus.PENDING)
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    # In-cluster Service DNS name once applied, e.g.
    # "http://qwen-7b.default.svc.cluster.local:8000/v1" -- reachable
    # from other pods on the target cluster, NOT from outside it (no
    # ingress/gateway wiring here -- see api/ai_workloads.py's docstring
    # for why that's deliberately left to the addon catalog's
    # apigateway/bgp-lb, not reinvented here).
    service_endpoint: Mapped[str | None] = mapped_column(String(500), nullable=True)
