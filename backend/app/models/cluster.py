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


class InfrastructureProvider(str, enum.Enum):
    """Which Cluster API infrastructure provider actually stands up the
    target cluster's nodes. Drives which Jinja template renders the
    Cluster/*Cluster/*MachineTemplate objects (see
    services/yaml_generator.py's PROVIDER_TEMPLATES) and whether the
    hardware-asset picker flow applies at all.

    METAL3: bare metal via baremetal-operator/Ironic -- the only provider
        with real physical HardwareAsset picking, CPU reservation, NIC
        bonding, all of it. Everything this project was originally built
        around.
    OPENSTACK: Cluster API Provider OpenStack (CAPO) -- VMs on an existing
        OpenStack cloud.
    VSPHERE: Cluster API Provider vSphere (CAPV) -- VMs on vCenter.
    KUBEVIRT: Cluster API Provider KubeVirt (CAPK) -- VMs running as
        KubeVirt VirtualMachines inside an existing (management) K8s
        cluster. This is the generic answer to "other KVM interfaces":
        KubeVirt itself runs on top of libvirt/QEMU-KVM, so anything that
        can host a KubeVirt-enabled cluster (bare metal or virtualized)
        works as the substrate.
    DOCKER: Cluster API Provider Docker (CAPD) -- each "machine" is a
        container (kindest/node images) on the management cluster's own
        Docker daemon. No physical hosts, no cloud account, no VMware.
        Upstream Cluster API's own explicitly-documented position: this
        is a development/testing provider, not a production one. Its
        entire purpose here is proving the pipeline (this backend -> CAPI
        manifests -> a real, reachable Kubernetes API server) works
        end to end without needing real infrastructure -- see
        deploy/testing/capd-quickstart/README.md.
    """

    METAL3 = "metal3"
    OPENSTACK = "openstack"
    VSPHERE = "vsphere"
    KUBEVIRT = "kubevirt"
    DOCKER = "docker"


class Cluster(TimestampedModel):
    """A target (production) Kubernetes cluster deployed via Cluster API."""

    __tablename__ = "clusters"

    name: Mapped[str] = mapped_column(String(253), unique=True, index=True)
    namespace: Mapped[str] = mapped_column(String(253), default="metal3")
    status: Mapped[ClusterStatus] = mapped_column(
        Enum(ClusterStatus), default=ClusterStatus.PENDING
    )
    infrastructure_provider: Mapped[InfrastructureProvider] = mapped_column(
        Enum(InfrastructureProvider), default=InfrastructureProvider.METAL3
    )
    control_plane_endpoint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    control_plane_count: Mapped[int] = mapped_column(default=3)
    worker_pool_config: Mapped[dict] = mapped_column(JSON, default=dict)
    # Free-form spec derived from the uploaded ccdadm-style config
    # (infra/networks/iaas/kubernetes sections). Never store raw secrets
    # here -- reference a secret name/path instead. Also where
    # provider-specific cloud config lives for non-metal3 clusters (e.g.
    # spec["openstack"] = {cloud_name, external_network_id, ...},
    # spec["vsphere"] = {server, datacenter, datastore, network, ...},
    # spec["kubevirt"] = {storage_class_name, namespace}) and where
    # control_plane_flavor/control_plane_image live for cloud providers.
    spec: Mapped[dict] = mapped_column(JSON, default=dict)
