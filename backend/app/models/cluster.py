import enum

from sqlalchemy import Enum, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedModel


class ClusterStatus(str, enum.Enum):
    PENDING = "pending"
    BOOTSTRAPPING = "bootstrapping"
    PROVISIONING = "provisioning"
    READY = "ready"
    FAILED = "failed"
    DELETING = "deleting"


class Cluster(TimestampedModel):
    """A target (production) Kubernetes cluster deployed via Cluster API."""

    __tablename__ = "clusters"

    name: Mapped[str] = mapped_column(String(253), unique=True, index=True)
    namespace: Mapped[str] = mapped_column(String(253), default="metal3")
    status: Mapped[ClusterStatus] = mapped_column(
        Enum(ClusterStatus), default=ClusterStatus.PENDING
    )
    control_plane_endpoint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    control_plane_count: Mapped[int] = mapped_column(default=3)
    worker_pool_config: Mapped[dict] = mapped_column(JSON, default=dict)
    # Free-form spec derived from the uploaded ccdadm-style config
    # (infra/networks/iaas/kubernetes sections). Never store raw secrets
    # here -- reference a secret name/path instead.
    spec: Mapped[dict] = mapped_column(JSON, default=dict)
