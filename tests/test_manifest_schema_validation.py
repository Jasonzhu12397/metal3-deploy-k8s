"""
Validates every manifest this project's YamlGeneratorService actually
renders, for ALL FIVE infrastructure providers, against the REAL
upstream CustomResourceDefinition schemas -- not a hand-approximated
schema, the actual openAPIV3Schema Kubernetes itself would enforce (see
backend/tests_data/crd_schemas/README.md for exactly where these came
from, which contract version each targets, and how to refresh them).

Every other test in this project either checks "is this valid YAML" or
mocks the Kubernetes layer entirely -- neither can catch a manifest with
the right field names and right YAML structure but a value of the wrong
*type*, or a reference field using a contract version's old shape. This
file exists because that gap is real: it caught real bugs on two
separate occasions during development, not hypothetical ones added
retroactively:

1. `checksum: {{ cluster.image_checksum | default('') }}` rendered
   `checksum: ` when no checksum was supplied, and an empty/absent YAML
   scalar parses as `null`, not empty string -- the (then-current)
   Metal3MachineTemplate CRD rejected that. Fixed by only emitting the
   key when there's a real value.
2. Migrating from the CAPI v1beta1 contract (deprecated as of CAPI
   v1.11.0) to v1beta2 changed `infrastructureRef`/`controlPlaneRef`/
   `configRef` from `{apiVersion, kind, name}` to `{apiGroup, kind, name}`,
   and `kubeletExtraArgs`/`apiServer.extraArgs` from a map to a list of
   `{name, value}` objects -- across all 5 provider templates. Metal3's
   own v1beta2 types separately renamed `noCloudProvider` to
   `cloudProviderEnabled`, `format` to `diskFormat`, and made `checksum`
   REQUIRED (the opposite of the v1beta1 fix in bug #1 above -- this
   file's tests for both "empty checksum" and "provided checksum" exist
   specifically because that requirement direction flipped once already).

What this does NOT prove: that a real Ironic/baremetal-operator/CAPM3/
CAPO/CAPV/CAPK controller would successfully *reconcile* these objects
into an actual running cluster (needs real infrastructure, or the
vm-bmc/capd-quickstart testing paths under deploy/testing/ -- see those
directories' own READMEs for what's verified vs. not there), or every
*semantic* constraint the real controllers enforce beyond what the CRD's
structural schema captures. What it DOES prove: a real Kubernetes API
server's structural admission validation would accept these objects.
"""
import os
import sys
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft4Validator

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.services.asset_planner import AssetPlannerService  # noqa: E402
from app.services.yaml_generator import YamlGeneratorService  # noqa: E402
from app.models.hardware_asset import HardwareAsset  # noqa: E402

CRD_DIR = Path(__file__).parent.parent / "backend" / "tests_data" / "crd_schemas"


def _extract_schema(crd_filename: str, version: str) -> dict:
    doc = yaml.safe_load((CRD_DIR / crd_filename).read_text())
    for v in doc["spec"]["versions"]:
        if v["name"] == version:
            return v["schema"]["openAPIV3Schema"]
    available = [v["name"] for v in doc["spec"]["versions"]]
    raise ValueError(f"{version} not found in {crd_filename}, available: {available}")


@pytest.fixture(scope="module")
def schemas() -> dict[tuple[str, str], dict]:
    """(apiVersion, kind) -> real openAPIV3Schema, loaded once per test
    module run. See backend/tests_data/crd_schemas/README.md's
    version-status table for why each (kind -> version) pairing here is
    what it is -- v1beta2 where this project's templates use v1beta2,
    v1beta1/v1alpha1 where a provider's own resources are deliberately
    still on those (documented, not an oversight)."""
    return {
        ("cluster.x-k8s.io/v1beta2", "Cluster"): _extract_schema("cluster.yaml", "v1beta2"),
        ("cluster.x-k8s.io/v1beta2", "MachineDeployment"): _extract_schema("machinedeployment.yaml", "v1beta2"),
        ("controlplane.cluster.x-k8s.io/v1beta2", "KubeadmControlPlane"): _extract_schema(
            "kubeadmcontrolplane.yaml", "v1beta2"
        ),
        ("bootstrap.cluster.x-k8s.io/v1beta2", "KubeadmConfigTemplate"): _extract_schema(
            "kubeadmconfigtemplate.yaml", "v1beta2"
        ),
        ("infrastructure.cluster.x-k8s.io/v1beta2", "Metal3Cluster"): _extract_schema(
            "metal3cluster.yaml", "v1beta2"
        ),
        ("infrastructure.cluster.x-k8s.io/v1beta2", "Metal3MachineTemplate"): _extract_schema(
            "metal3machinetemplate.yaml", "v1beta2"
        ),
        ("metal3.io/v1alpha1", "BareMetalHost"): _extract_schema("baremetalhost.yaml", "v1alpha1"),
        ("infrastructure.cluster.x-k8s.io/v1beta2", "DockerCluster"): _extract_schema(
            "dockercluster.yaml", "v1beta2"
        ),
        ("infrastructure.cluster.x-k8s.io/v1beta2", "DockerMachineTemplate"): _extract_schema(
            "dockermachinetemplate.yaml", "v1beta2"
        ),
        ("infrastructure.cluster.x-k8s.io/v1beta1", "OpenStackCluster"): _extract_schema(
            "openstackcluster.yaml", "v1beta1"
        ),
        ("infrastructure.cluster.x-k8s.io/v1beta1", "OpenStackMachineTemplate"): _extract_schema(
            "openstackmachinetemplate.yaml", "v1beta1"
        ),
        ("infrastructure.cluster.x-k8s.io/v1beta1", "VSphereCluster"): _extract_schema(
            "vspherecluster.yaml", "v1beta1"
        ),
        ("infrastructure.cluster.x-k8s.io/v1beta1", "VSphereMachineTemplate"): _extract_schema(
            "vspheremachinetemplate.yaml", "v1beta1"
        ),
        # KubevirtCluster/KubevirtMachineTemplate (v1alpha1) intentionally
        # absent -- see fixtures README. test_kubevirt_provider_* below
        # explicitly tells _assert_all_valid to expect and skip those two
        # kinds rather than silently ignoring an unregistered schema.
    }


def _assert_all_valid(
    docs: list[dict], schemas: dict, expected_unvalidated_kinds: frozenset[str] = frozenset()
) -> None:
    failures = []
    validated_count = 0
    for doc in docs:
        key = (doc.get("apiVersion"), doc.get("kind"))
        name = doc.get("metadata", {}).get("name", "?")
        schema = schemas.get(key)
        if schema is None:
            if doc.get("kind") in expected_unvalidated_kinds:
                continue
            failures.append(f"{doc.get('kind')}/{name}: no schema registered for {key}")
            continue
        validated_count += 1
        errors = list(Draft4Validator(schema).iter_errors(doc))
        for e in errors:
            path = ".".join(str(p) for p in e.path) or "(root)"
            failures.append(f"{doc.get('kind')}/{name}: {path}: {e.message}")

    assert validated_count > 0, "no resources were actually validated -- test setup is broken"
    assert not failures, "Manifest(s) would be REJECTED by a real Kubernetes API server:\n" + "\n".join(failures)


def _asset(name: str, index: int = 0) -> HardwareAsset:
    return HardwareAsset(
        name=name,
        cpu_sockets=2,
        cpu_cores_per_socket=32,
        cpu_threads_per_core=2,
        memory_gb=256,
        bmc_address=f"redfish://192.0.2.{10 + index}/redfish/v1/Systems/1",
        boot_mac_address=f"aa:bb:cc:dd:ee:{index:02d}",
        gpu_model=None,
        gpu_count=0,
        gpu_memory_gb=None,
    )


def _assignment(role: str):
    from types import SimpleNamespace

    return SimpleNamespace(
        role=role,
        reserved_cores_per_socket=4,
        cpu_manager_policy="static",
        topology_manager_policy="single-numa-node",
        isolation_interrupts=False,
        hugepage_type="1GB",
        hugepage_count_1gb=16,
        hugepage_count_2mb=0,
    )


def _render_metal3(planner: AssetPlannerService, cluster_spec: dict, pools: dict) -> list[dict]:
    bundle = planner.generate_bundle(cluster_spec, pools)
    return planner.yaml_gen.parse_multi(bundle["cluster_config_yaml"]) + planner.yaml_gen.parse_multi(
        bundle["bmh_yaml"]
    )


# ---------------------------------------------------------------------
# Metal3 -- the provider this whole test file exists because of
# ---------------------------------------------------------------------


def test_metal3_single_node_cluster_without_image_checksum(schemas):
    """The exact case that caught the original bug: no image_checksum
    supplied at all."""
    planner = AssetPlannerService()
    pools = {"control-plane": ([_asset("cp-01")], [_assignment("control-plane")])}
    docs = _render_metal3(
        planner, {"name": "single-node", "namespace": "metal3", "control_plane_endpoint": "192.0.2.1"}, pools
    )
    _assert_all_valid(docs, schemas)


def test_metal3_single_node_cluster_with_image_checksum(schemas):
    planner = AssetPlannerService()
    pools = {"control-plane": ([_asset("cp-01")], [_assignment("control-plane")])}
    docs = _render_metal3(
        planner,
        {
            "name": "single-node-checksummed",
            "namespace": "metal3",
            "control_plane_endpoint": "192.0.2.1",
            "image_checksum": "abc123def456",
            "image_checksum_type": "sha256",
        },
        pools,
    )
    _assert_all_valid(docs, schemas)


def test_metal3_ha_cluster_with_control_plane_and_worker_pools(schemas):
    planner = AssetPlannerService()
    pools = {
        "control-plane": (
            [_asset("cp-0", 0), _asset("cp-1", 1), _asset("cp-2", 2)],
            [_assignment("control-plane")] * 3,
        ),
        "workers": ([_asset("wk-0", 3), _asset("wk-1", 4)], [_assignment("worker")] * 2),
    }
    docs = _render_metal3(
        planner, {"name": "ha-cluster", "namespace": "metal3", "control_plane_endpoint": "192.0.2.100"}, pools
    )
    assert len(docs) == 12
    _assert_all_valid(docs, schemas)


def test_metal3_gpu_pool_labels_are_still_schema_valid(schemas):
    """GPU support adds node_labels entries like 'gpu=true' -- confirm
    those survive the kubeletExtraArgs map->list conversion without
    producing something the real schema would reject."""
    planner = AssetPlannerService()
    gpu_asset = HardwareAsset(
        name="gpu-01",
        cpu_sockets=2,
        cpu_cores_per_socket=32,
        cpu_threads_per_core=2,
        memory_gb=512,
        gpu_model="NVIDIA H100 80GB",
        gpu_count=8,
        gpu_memory_gb=80,
        bmc_address="redfish://192.0.2.50/redfish/v1/Systems/1",
        boot_mac_address="aa:bb:cc:dd:ee:50",
    )
    pools = {
        "control-plane": ([_asset("cp-01")], [_assignment("control-plane")]),
        "gpu-pool": ([gpu_asset], [_assignment("worker")]),
    }
    docs = _render_metal3(
        planner, {"name": "gpu-cluster", "namespace": "metal3", "control_plane_endpoint": "192.0.2.1"}, pools
    )
    _assert_all_valid(docs, schemas)


def test_deliberately_broken_manifest_is_caught_by_this_test_harness(schemas):
    """Meta-test: proves _assert_all_valid actually fails on a genuinely
    invalid object, rather than silently passing everything (which would
    make every test in this file worthless)."""
    broken = [
        {
            "apiVersion": "infrastructure.cluster.x-k8s.io/v1beta2",
            "kind": "Metal3MachineTemplate",
            "metadata": {"name": "broken", "namespace": "metal3"},
            "spec": {"template": {"spec": {"image": {"url": "http://x/y.qcow2", "checksum": None}}}},
        }
    ]
    with pytest.raises(AssertionError, match="would be REJECTED"):
        _assert_all_valid(broken, schemas)


# ---------------------------------------------------------------------
# The other 4 providers -- CAPI-core resources validated for all of
# them; provider-specific resources validated too where this project
# deliberately kept a schema on hand (docker: v1beta2; openstack/vsphere:
# v1beta1). kubevirt's provider-specific resources are the one
# exception, expected and asserted explicitly below.
# ---------------------------------------------------------------------


def test_docker_provider_end_to_end(schemas):
    gen = YamlGeneratorService()
    spec = {
        "name": "dockertest",
        "namespace": "metal3",
        "infrastructure_provider": "docker",
        "control_plane_count": 1,
        "worker_pools": [{"name": "workers", "count": 2, "node_labels": ["role=demo"]}],
    }
    docs = gen.parse_multi(gen.render_cluster_config(spec))
    _assert_all_valid(docs, schemas)


def test_openstack_provider_end_to_end(schemas):
    gen = YamlGeneratorService()
    spec = {
        "name": "osttest",
        "namespace": "metal3",
        "infrastructure_provider": "openstack",
        "control_plane_count": 3,
        "control_plane_endpoint": "192.0.2.1",
        "control_plane_flavor": "m1.large",
        "control_plane_image": "ubuntu-22.04",
        "control_plane_reserved_cpus": "0,1,2,3",
        "worker_pools": [
            {
                "name": "workers",
                "count": 2,
                "flavor": "m1.medium",
                "image": "ubuntu-22.04",
                "node_labels": ["role=test"],
                "reserved_cpus": "0,1",
            }
        ],
        "openstack": {
            "cloud_name": "mycloud",
            "external_network_id": "abc-123",
            "ssh_key_name": "mykey",
            "security_groups": ["default"],
        },
    }
    docs = gen.parse_multi(gen.render_cluster_config(spec))
    _assert_all_valid(docs, schemas)


def test_vsphere_provider_end_to_end(schemas):
    gen = YamlGeneratorService()
    spec = {
        "name": "vstest",
        "namespace": "metal3",
        "infrastructure_provider": "vsphere",
        "control_plane_count": 3,
        "control_plane_endpoint": "192.0.2.1",
        "control_plane_flavor": "",
        "control_plane_image": "ubuntu-template",
        "worker_pools": [{"name": "workers", "count": 2, "flavor": "", "image": "ubuntu-template"}],
        "vsphere": {
            "server": "vcenter.local",
            "datacenter": "dc1",
            "datastore": "ds1",
            "network": "net1",
            "resource_pool": "rp1",
            "folder": "vms",
        },
    }
    docs = gen.parse_multi(gen.render_cluster_config(spec))
    _assert_all_valid(docs, schemas)


def test_kubevirt_provider_shared_capi_core_resources(schemas):
    """KubevirtCluster/KubevirtMachineTemplate (v1alpha1) aren't
    schema-validated here -- see fixtures README for why -- so this
    explicitly tells _assert_all_valid to expect and ignore exactly
    those two kinds, while everything else rendered (the v1beta2
    CAPI-core resources) still gets fully checked."""
    gen = YamlGeneratorService()
    spec = {
        "name": "kvtest",
        "namespace": "metal3",
        "infrastructure_provider": "kubevirt",
        "control_plane_count": 1,
        "control_plane_endpoint": "192.0.2.1",
        "control_plane_flavor": "",
        "control_plane_image": "kubevirt-image",
        "worker_pools": [{"name": "workers", "count": 1, "flavor": "", "image": "kubevirt-image"}],
        "kubevirt": {"storage_class_name": "local-path"},
    }
    docs = gen.parse_multi(gen.render_cluster_config(spec))
    _assert_all_valid(
        docs, schemas, expected_unvalidated_kinds=frozenset({"KubevirtCluster", "KubevirtMachineTemplate"})
    )
