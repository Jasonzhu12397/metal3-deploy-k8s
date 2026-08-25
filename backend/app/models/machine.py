import enum

from sqlalchemy import ForeignKey, String, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedModel


class MachineRole(str, enum.Enum):
    CONTROL_PLANE = "control-plane"
    WORKER = "worker"


class Machine(TimestampedModel):
    """Mirrors a Cluster API Machine object bound to a BareMetalHost."""

    __tablename__ = "machines"

    name: Mapped[str] = mapped_column(String(253), unique=True, index=True)
    role: Mapped[MachineRole] = mapped_column(Enum(MachineRole))
    cluster_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clusters.id"))
    baremetalhost_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("baremetal_hosts.id"), nullable=True
    )
    phase: Mapped[str] = mapped_column(String(64), default="Pending")
