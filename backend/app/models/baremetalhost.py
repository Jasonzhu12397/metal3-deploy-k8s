import enum

from sqlalchemy import ForeignKey, String, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedModel


class BMHState(str, enum.Enum):
    UNKNOWN = "unknown"
    REGISTERING = "registering"
    INSPECTING = "inspecting"
    AVAILABLE = "available"
    PROVISIONING = "provisioning"
    PROVISIONED = "provisioned"
    DEPROVISIONING = "deprovisioning"
    ERROR = "error"


class BareMetalHost(TimestampedModel):
    """Mirrors a metal3.io BareMetalHost object; BMC credentials are stored
    as a reference to a Kubernetes Secret name, never inline."""

    __tablename__ = "baremetal_hosts"

    name: Mapped[str] = mapped_column(String(253), unique=True, index=True)
    node_pool_name: Mapped[str] = mapped_column(String(128), index=True)
    bmc_address: Mapped[str] = mapped_column(String(255))
    bmc_credentials_secret: Mapped[str] = mapped_column(String(253))
    boot_mac_address: Mapped[str] = mapped_column(String(17))
    online: Mapped[bool] = mapped_column(default=False)
    state: Mapped[BMHState] = mapped_column(Enum(BMHState), default=BMHState.UNKNOWN)
    cluster_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clusters.id", ondelete="SET NULL"), nullable=True
    )
