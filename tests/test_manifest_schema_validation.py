"""
Validates every manifest this project's YamlGeneratorService actually
renders against the REAL upstream CustomResourceDefinition schemas for
Cluster API core + Cluster API Provider Metal3 + baremetal-operator --
not a hand-approximated schema, the actual openAPIV3Schema Kubernetes
itself would enforce (see backend/tests_data/crd_schemas/README.md for
exactly where these came from and how to refresh them).

Every other test in this project either checks "is this valid YAML" or
mocks the Kubernetes layer entirely -- neither can catch a manifest with
the right field names and right YAML structure but a value of the wrong
*type*, which is exactly what a real API server rejects on `kubectl
apply`. This file exists because that gap is real: it caught an actual
bug during development (not a hypothetical one added retroactively) --
`checksum: {{ cluster.image_checksum | default('') }}` rendered
`checksum: ` when no checksum was supplied, and an empty/absent YAML
scalar parses as `null`, not empty string, which the real
Metal3MachineTemplate CRD rejects (checksum, when present, must be a
string). Fixed by only emitting the key when there's a real value --
see templates/capi/cluster-template.yaml.j2's image block.

What this does NOT prove: that a real Ironic/baremetal-operator/CAPM3
controller would successfully reconcile these objects into an actual
running cluster (needs real hardware or the vm-bmc/capd-quickstart
testing paths, see deploy/testing/), or that these objects satisfy every
*semantic* constraint the real controllers enforce beyond what the CRD's
structural schema captures (e.g. the schema doesn't require
infrastructureRef to point at a Metal3Cluster that actually exists --
that's runtime reconciliation logic, not admission-time schema
validation). What it DOES prove: a real Kubernetes API server's
structural admission validation would accept these objects, which is a
categorically stronger claim than "this parses as YAML".
"""
import os
import sys
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft4Validator

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.services.asset_planner import AssetPlannerService  # noqa: E402
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
    module run (these files are large; re-parsing per-test would be
    needlessly slow)."""
    return {
        ("cluster.x-k8s.io/v1beta1", "Cluster"): _extract_schema("cluster.yaml", "v1beta1"),
        ("cluster.x-k8s.io/v1beta1", "MachineDeployment"): _extract_schema("machinedeployment.yaml", "v1beta1"),
        ("controlplane.cluster.x-k8s.io/v1beta1", "KubeadmControlPlane"): _extract_schema(
            "kubeadmcontrolplane.yaml", "v1beta1"
        ),
        ("bootstrap.cluster.x-k8s.io/v1beta1", "KubeadmConfigTemplate"): _extract_schema(
            "kubeadmconfigtemplate.yaml", "v1beta1"
        ),
        ("infrastructure.cluster.x-k8s.io/v1beta1", "Metal3Cluster"): _extract_schema(
            "metal3cluster.yaml", "v1beta1"
        ),
        ("infrastructure.cluster.x-k8s.io/v1beta1", "Metal3MachineTemplate"): _extract_schema(
            "metal3machinetemplate.yaml", "v1beta1"
        ),
        ("metal3.io/v1alpha1", "BareMetalHost"): _extract_schema("baremetalhost.yaml", "v1alpha1"),
    }


def _assert_all_valid(docs: list[dict], schemas: dict) -> None:
    failures = []
    validated_count = 0
    for doc in docs:
        key = (doc.get("apiVersion"), doc.get("kind"))
        name = doc.get("metadata", {}).get("name", "?")
        schema = schemas.get(key)
        if schema is None:
            # Every kind this project's metal3 templates render has a
            # schema above -- an unrecognized kind here means either a
            # new resource type was added to the templates without
            # updating this test, or a typo'd apiVersion/kind. Either
            # way, silently skipping would defeat the point.
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


def _render_all(planner: AssetPlannerService, cluster_spec: dict, pools: dict) -> list[dict]:
    bundle = planner.generate_bundle(cluster_spec, pools)
    return planner.yaml_gen.parse_multi(bundle["cluster_config_yaml"]) + planner.yaml_gen.parse_multi(
        bundle["bmh_yaml"]
    )


def test_single_node_cluster_without_image_checksum(schemas):
    """The exact case that caught the real bug: no image_checksum
    supplied at all. Before the fix, this produced checksum: null on
    Metal3MachineTemplate, which the real CRD rejects (checksum, if
    present, must be a string -- see tests_data/crd_schemas' module
    docstring above)."""
    planner = AssetPlannerService()
    pools = {"control-plane": ([_asset("cp-01")], [_assignment("control-plane")])}
    docs = _render_all(
        planner, {"name": "single-node", "namespace": "metal3", "control_plane_endpoint": "192.0.2.1"}, pools
    )
    _assert_all_valid(docs, schemas)


def test_single_node_cluster_with_image_checksum(schemas):
    planner = AssetPlannerService()
    pools = {"control-plane": ([_asset("cp-01")], [_assignment("control-plane")])}
    docs = _render_all(
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


def test_ha_cluster_with_control_plane_and_worker_pools(schemas):
    planner = AssetPlannerService()
    pools = {
        "control-plane": ([_asset("cp-0", 0), _asset("cp-1", 1), _asset("cp-2", 2)], [_assignment("control-plane")] * 3),
        "workers": ([_asset("wk-0", 3), _asset("wk-1", 4)], [_assignment("worker")] * 2),
    }
    docs = _render_all(
        planner, {"name": "ha-cluster", "namespace": "metal3", "control_plane_endpoint": "192.0.2.100"}, pools
    )
    assert len(docs) == 12  # Cluster, Metal3Cluster, 2x(Metal3MachineTemplate), KubeadmControlPlane,
    # KubeadmConfigTemplate, MachineDeployment, 5x BareMetalHost
    _assert_all_valid(docs, schemas)


def test_gpu_pool_labels_are_still_schema_valid(schemas):
    """GPU support (see backend/tests/test_gpu_hardware.py) adds
    node_labels entries like 'gpu=true' -- confirm those don't somehow
    produce a KubeadmConfigTemplate/KubeadmControlPlane the real schema
    would reject (e.g. via an unexpected type in kubeletExtraArgs)."""
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
    docs = _render_all(
        planner, {"name": "gpu-cluster", "namespace": "metal3", "control_plane_endpoint": "192.0.2.1"}, pools
    )
    _assert_all_valid(docs, schemas)


def test_deliberately_broken_manifest_is_caught_by_this_test_harness(schemas):
    """Meta-test: proves _assert_all_valid actually fails on a genuinely
    invalid object, rather than silently passing everything (which would
    make every test above worthless)."""
    broken = [
        {
            "apiVersion": "infrastructure.cluster.x-k8s.io/v1beta1",
            "kind": "Metal3MachineTemplate",
            "metadata": {"name": "broken", "namespace": "metal3"},
            "spec": {"template": {"spec": {"image": {"url": "http://x/y.qcow2", "checksum": None}}}},
        }
    ]
    with pytest.raises(AssertionError, match="would be REJECTED"):
        _assert_all_valid(broken, schemas)
