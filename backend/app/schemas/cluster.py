from __future__ import annotations

import uuid
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator

from app.models.cluster import ClusterStatus, InfrastructureProvider


class WorkerPoolSpec(BaseModel):
    name: str
    count: int
    role: str = "worker"
    node_labels: list[str] = Field(default_factory=list)
    hugepage_type: Optional[str] = None
    reserved_cpus: Optional[str] = None
    # Cloud-provider pools only (infrastructure_provider != metal3): there's
    # no physical HardwareAsset to pick for a VM, so the machine spec is
    # just declared directly. Ignored for metal3, where the equivalent
    # comes from whatever HardwareAsset actually gets assigned to the pool.
    flavor: Optional[str] = Field(
        None, description="OpenStack flavor name / vSphere sizing preset / ignored for kubevirt"
    )
    image: Optional[str] = Field(
        None, description="OpenStack/vSphere image or template name, or a KubeVirt DataVolume/boot source name"
    )


class ClusterCreate(BaseModel):
    name: str = Field(..., description="Cluster name, e.g. prod-cluster-01")
    namespace: str = "metal3"
    infrastructure_provider: InfrastructureProvider = InfrastructureProvider.METAL3
    control_plane_count: int = 3
    control_plane_endpoint: Optional[str] = None
    # Cloud-provider control-plane machine spec (ignored for metal3).
    control_plane_flavor: Optional[str] = None
    control_plane_image: Optional[str] = None
    worker_pools: list[WorkerPoolSpec] = Field(default_factory=list)
    # Arbitrary extra spec (pod/service CIDRs, networks, iaas, etc.),
    # plus provider-specific cloud config for non-metal3 clusters, e.g.:
    #   openstack: {cloud_name, external_network_id, availability_zone}
    #   vsphere:   {server, datacenter, datastore, network, resource_pool}
    #   kubevirt:  {storage_class_name, namespace}
    spec: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _cloud_providers_need_a_machine_spec(self) -> "ClusterCreate":
        # metal3: machine spec comes from the HardwareAsset assigned to
        # each pool, not from this form. docker (CAPD): the whole point
        # is zero external dependencies -- DockerMachineTemplate doesn't
        # take a flavor/image at all, the node image is derived from the
        # Kubernetes version instead (see templates/capi/providers/docker.yaml.j2).
        # Every OTHER provider is a real cloud/VM backend that genuinely
        # needs these to know what to boot.
        if self.infrastructure_provider in (InfrastructureProvider.METAL3, InfrastructureProvider.DOCKER):
            return self
        if not self.control_plane_flavor or not self.control_plane_image:
            raise ValueError(
                f"infrastructure_provider={self.infrastructure_provider.value} needs "
                "control_plane_flavor and control_plane_image (there's no HardwareAsset "
                "to derive a machine spec from for a cloud/VM-based provider)"
            )
        for pool in self.worker_pools:
            if not pool.flavor or not pool.image:
                raise ValueError(
                    f"worker pool '{pool.name}' needs flavor and image for a "
                    f"{self.infrastructure_provider.value} cluster"
                )
        return self


class ClusterRead(BaseModel):
    id: uuid.UUID
    name: str
    namespace: str
    status: ClusterStatus
    infrastructure_provider: InfrastructureProvider
    control_plane_endpoint: Optional[str] = None
    control_plane_count: int
    worker_pool_config: dict[str, Any]
    spec: dict[str, Any] = Field(default_factory=dict)

    class Config:
        from_attributes = True


class ClusterUpdate(BaseModel):
    control_plane_endpoint: Optional[str] = None
    status: Optional[ClusterStatus] = None
