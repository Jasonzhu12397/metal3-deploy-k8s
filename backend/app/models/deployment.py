import enum

from sqlalchemy import ForeignKey, String, Enum, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedModel


class DeploymentPhase(str, enum.Enum):
    QUEUED = "queued"
    GENERATING_MANIFESTS = "generating_manifests"
    BOOTSTRAPPING_EPHEMERAL_NODE = "bootstrapping_ephemeral_node"
    APPLYING_BMH = "applying_bmh"
    WAITING_FOR_HOSTS = "waiting_for_hosts"
    APPLYING_CLUSTER = "applying_cluster"
    WAITING_FOR_CONTROL_PLANE = "waiting_for_control_plane"
    INSTALLING_ADDONS = "installing_addons"
    PIVOTING_TO_TARGET_CLUSTER = "pivoting_to_target_cluster"
    COMPLETE = "complete"
    FAILED = "failed"


class Deployment(TimestampedModel):
    """A single end-to-end run of: ephemeral node -> Metal3/BMH -> CAPI
    cluster -> addons, driven from the uploaded bmh.yaml / k8s-config.yaml
    / eph-net.yaml style inputs."""

    __tablename__ = "deployments"

    cluster_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clusters.id"))
    phase: Mapped[DeploymentPhase] = mapped_column(
        Enum(DeploymentPhase), default=DeploymentPhase.QUEUED
    )
    celery_task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    log: Mapped[str | None] = mapped_column(Text, nullable=True)
