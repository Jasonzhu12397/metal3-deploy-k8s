"""
Covers app/services/cloud_planner.py (CloudPlannerService) -- found via a
bug-scanning pass (grep across tests/*.py for any reference to this
service or module name) to have ZERO test coverage, despite being the
entire spec-building step for every non-metal3 provider's deployment
path (openstack/vsphere/kubevirt/docker all go through
build_cluster_spec before rendering). test_cloud_providers.py exercises
the TEMPLATE rendering with hand-built cluster_spec dicts -- it never
actually calls CloudPlannerService itself, so the "turn a Cluster ORM
row into that dict" step had no coverage at all.
"""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.services.cloud_planner import CloudPlannerService  # noqa: E402
from app.models.cluster import InfrastructureProvider  # noqa: E402


def _fake_cluster(**overrides) -> SimpleNamespace:
    """A lightweight stand-in for the Cluster ORM model -- only needs
    the attributes build_cluster_spec actually reads."""
    defaults = dict(
        name="test-cluster",
        namespace="metal3",
        infrastructure_provider=InfrastructureProvider.OPENSTACK,
        control_plane_count=3,
        control_plane_endpoint="192.0.2.1",
        worker_pool_config={"pools": []},
        spec={},
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_build_cluster_spec_includes_core_fields():
    planner = CloudPlannerService()
    cluster = _fake_cluster()
    spec = planner.build_cluster_spec(cluster)
    assert spec["name"] == "test-cluster"
    assert spec["namespace"] == "metal3"
    assert spec["infrastructure_provider"] == "openstack"
    assert spec["control_plane_count"] == 3
    assert spec["control_plane_endpoint"] == "192.0.2.1"


def test_build_cluster_spec_always_sets_empty_hosts():
    """No physical hosts for a cloud provider -- deployment_tasks.py
    relies on this list being present and empty to skip
    APPLYING_BMH/WAITING_FOR_HOSTS entirely."""
    planner = CloudPlannerService()
    spec = planner.build_cluster_spec(_fake_cluster())
    assert spec["hosts"] == []


def test_build_cluster_spec_extracts_worker_pools_from_config():
    planner = CloudPlannerService()
    cluster = _fake_cluster(
        worker_pool_config={"pools": [{"name": "workers", "count": 2, "flavor": "m1.large", "image": "ubuntu-22.04"}]}
    )
    spec = planner.build_cluster_spec(cluster)
    assert spec["worker_pools"] == [{"name": "workers", "count": 2, "flavor": "m1.large", "image": "ubuntu-22.04"}]


def test_build_cluster_spec_spreads_arbitrary_spec_fields():
    """cluster.spec is the free-form bucket for provider-specific config
    (openstack.cloud_name, vsphere.server, pod_cidr, etc.) -- must be
    spread directly into the top-level dict the templates read from."""
    planner = CloudPlannerService()
    cluster = _fake_cluster(spec={"openstack": {"cloud_name": "mycloud"}, "pod_cidr": "10.244.0.0/16"})
    spec = planner.build_cluster_spec(cluster)
    assert spec["openstack"] == {"cloud_name": "mycloud"}
    assert spec["pod_cidr"] == "10.244.0.0/16"


def test_build_cluster_spec_guarantees_provider_config_subdict_exists():
    """Even with nothing provider-specific supplied, the provider's own
    config sub-dict (openstack/vsphere/kubevirt) must exist as at least
    an empty dict -- templates read e.g. cluster.vsphere.server under
    Jinja's StrictUndefined, which raises on a genuinely missing key,
    not just a missing value."""
    planner = CloudPlannerService()
    cluster = _fake_cluster(infrastructure_provider=InfrastructureProvider.VSPHERE, spec={})
    spec = planner.build_cluster_spec(cluster)
    assert spec["vsphere"] == {}


def test_build_cluster_spec_does_not_overwrite_explicit_provider_config():
    planner = CloudPlannerService()
    cluster = _fake_cluster(
        infrastructure_provider=InfrastructureProvider.VSPHERE,
        spec={"vsphere": {"server": "vcenter.local"}},
    )
    spec = planner.build_cluster_spec(cluster)
    assert spec["vsphere"] == {"server": "vcenter.local"}


def test_build_cluster_spec_handles_none_worker_pool_config_without_crashing():
    """Defensive: nothing in the normal API path should ever store NULL
    for worker_pool_config (schemas guarantee a dict), but this function
    reads straight from a DB row, and a row is not a type-checked value
    -- must degrade to an empty pool list rather than raising
    AttributeError on None.get(...)."""
    planner = CloudPlannerService()
    cluster = _fake_cluster(worker_pool_config=None)
    spec = planner.build_cluster_spec(cluster)
    assert spec["worker_pools"] == []


def test_build_cluster_spec_handles_none_spec_without_crashing():
    """Same defensive reasoning: **None used to raise TypeError
    immediately -- must degrade to no extra fields instead."""
    planner = CloudPlannerService()
    cluster = _fake_cluster(spec=None)
    spec = planner.build_cluster_spec(cluster)
    assert spec["name"] == "test-cluster"  # got this far without raising


def test_build_cluster_spec_handles_enum_or_plain_string_provider():
    """infrastructure_provider may come through as the InfrastructureProvider
    enum (the normal ORM case) or, in principle, a plain string -- both
    must resolve to the same plain string value templates key off of."""
    planner = CloudPlannerService()

    spec_from_enum = planner.build_cluster_spec(_fake_cluster(infrastructure_provider=InfrastructureProvider.DOCKER))
    assert spec_from_enum["infrastructure_provider"] == "docker"

    spec_from_string = planner.build_cluster_spec(_fake_cluster(infrastructure_provider="docker"))
    assert spec_from_string["infrastructure_provider"] == "docker"


def test_generate_cluster_config_yaml_produces_real_manifests():
    """End-to-end through the actual YamlGeneratorService, not just the
    dict-building step in isolation -- confirms build_cluster_spec's
    output is actually usable by the real template renderer, for every
    non-metal3 provider."""
    import yaml as pyyaml

    planner = CloudPlannerService()
    cluster = _fake_cluster(
        infrastructure_provider=InfrastructureProvider.DOCKER,
        control_plane_count=1,
        control_plane_endpoint=None,
        worker_pool_config={"pools": []},
        spec={},
    )
    rendered = planner.generate_cluster_config_yaml(cluster)
    docs = list(pyyaml.safe_load_all(rendered))
    kinds = [d["kind"] for d in docs if d]
    assert "Cluster" in kinds
    assert "DockerCluster" in kinds
