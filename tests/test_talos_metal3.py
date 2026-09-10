"""
Covers templates/capi/providers/talos-metal3.yaml.j2 -- Talos Linux as
the target OS on real bare-metal hardware via Metal3/Ironic, instead of
a traditional Linux distro bootstrapped via kubeadm.

Modeled as a "flavor" of the existing metal3 provider
(cluster_spec["os_flavor"] == "talos"), not a new top-level
infrastructure_provider -- Talos-on-Metal3 still needs real
BareMetalHost/Ironic hardware picking, the exact same
AssetPlannerService code path standard metal3 already uses, just with a
different control-plane/bootstrap stack on top (TalosControlPlane/
TalosConfigTemplate instead of KubeadmControlPlane/KubeadmConfigTemplate,
since Talos doesn't support kubeadm-style bootstrapping at all).

Validated against the REAL CustomResourceDefinition schemas from Talos's
own Cluster API provider pair -- Cluster API Bootstrap Provider Talos
(CABPT) and Cluster API Control Plane Provider Talos (CACPPT), both by
Sidero Labs -- snapshotted in backend/tests_data/crd_schemas/talos-*.yaml,
same rigor as this project's other provider templates. Confirmed while
building this: Talos's own CAPI providers are architecturally a
generation behind core CAPI/CAPM3 -- TalosControlPlane and
TalosConfigTemplate are only served at v1alpha3 (there's no v1beta1/
v1beta2 for these two types to have moved to), and their own object
references use the older {apiVersion, kind, name} ObjectReference shape
rather than the {apiGroup, kind, name} shape v1beta2 Cluster/
MachineDeployment use elsewhere in this same rendered bundle. Both facts
are accurate, not something to "fix" to match the rest of this project's
v1beta2 migration.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import yaml  # noqa: E402
from jsonschema import Draft4Validator  # noqa: E402

from app.services.asset_planner import AssetPlannerService  # noqa: E402
from app.models.hardware_asset import HardwareAsset  # noqa: E402

CRD_DIR = os.path.join(os.path.dirname(__file__), "..", "backend", "tests_data", "crd_schemas")


def _extract_all_versions(crd_filename: str) -> dict:
    docs = list(yaml.safe_load_all(open(os.path.join(CRD_DIR, crd_filename))))
    result = {}
    for d in docs:
        if d and d.get("kind") == "CustomResourceDefinition":
            for v in d["spec"]["versions"]:
                key = (d["spec"]["group"], d["spec"]["names"]["kind"], v["name"])
                result[key] = v["schema"]["openAPIV3Schema"]
    return result


def _load_core_schema(filename: str, version: str) -> dict:
    doc = yaml.safe_load(open(os.path.join(CRD_DIR, filename)))
    for v in doc["spec"]["versions"]:
        if v["name"] == version:
            return v["schema"]["openAPIV3Schema"]
    raise ValueError(f"{version} not found in {filename}")


def _schemas() -> dict:
    schemas = {}
    schemas.update(_extract_all_versions("talos-bootstrap.yaml"))
    schemas.update(_extract_all_versions("talos-controlplane.yaml"))
    schemas[("cluster.x-k8s.io", "Cluster", "v1beta2")] = _load_core_schema("cluster.yaml", "v1beta2")
    schemas[("infrastructure.cluster.x-k8s.io", "Metal3Cluster", "v1beta2")] = _load_core_schema(
        "metal3cluster.yaml", "v1beta2"
    )
    schemas[("infrastructure.cluster.x-k8s.io", "Metal3MachineTemplate", "v1beta2")] = _load_core_schema(
        "metal3machinetemplate.yaml", "v1beta2"
    )
    schemas[("cluster.x-k8s.io", "MachineDeployment", "v1beta2")] = _load_core_schema(
        "machinedeployment.yaml", "v1beta2"
    )
    return schemas


def _assert_all_valid(docs: list[dict]) -> None:
    schemas = _schemas()
    failures = []
    validated = 0
    for doc in docs:
        group, version = doc["apiVersion"].split("/")
        key = (group, doc["kind"], version)
        schema = schemas.get(key)
        if schema is None:
            failures.append(f"{doc['kind']}/{doc['metadata']['name']}: no schema for {key}")
            continue
        validated += 1
        for e in Draft4Validator(schema).iter_errors(doc):
            path = ".".join(str(p) for p in e.path) or "(root)"
            failures.append(f"{doc['kind']}/{doc['metadata']['name']}: {path}: {e.message}")
    assert validated > 0, "nothing was actually validated -- test setup is broken"
    assert not failures, "would be REJECTED by a real Kubernetes API server:\n" + "\n".join(failures)


def _asset(name: str, index: int = 0) -> HardwareAsset:
    return HardwareAsset(
        name=name,
        cpu_sockets=2,
        cpu_cores_per_socket=32,
        cpu_threads_per_core=2,
        memory_gb=128,
        bmc_address=f"redfish://192.0.2.{20 + index}/redfish/v1/Systems/1",
        boot_mac_address=f"aa:bb:cc:dd:ee:{20 + index:02x}",
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
        hugepage_count_1gb=8,
        hugepage_count_2mb=0,
    )


def test_talos_flavor_renders_through_the_real_asset_planner_hardware_picking_path():
    """The important architectural point, not just template rendering in
    isolation: Talos-on-Metal3 goes through AssetPlannerService.generate_bundle
    -- the exact same real hardware-picking / CPU-topology-math path
    standard metal3 clusters use -- not some separate, untested code path."""
    planner = AssetPlannerService()
    pools = {"control-plane": ([_asset("talos-cp-0")], [_assignment("control-plane")])}
    bundle = planner.generate_bundle(
        {
            "name": "talos-cluster",
            "namespace": "metal3",
            "control_plane_endpoint": "192.0.2.100",
            "os_flavor": "talos",
        },
        pools,
    )
    docs = planner.yaml_gen.parse_multi(bundle["cluster_config_yaml"])
    kinds = [d["kind"] for d in docs]
    assert kinds == ["Cluster", "Metal3Cluster", "Metal3MachineTemplate", "TalosControlPlane"]

    bmh_docs = planner.yaml_gen.parse_multi(bundle["bmh_yaml"])
    assert bmh_docs[0]["kind"] == "BareMetalHost"
    assert bmh_docs[0]["metadata"]["name"] == "talos-cp-0"

    _assert_all_valid(docs)


def test_talos_flavor_with_worker_pool():
    planner = AssetPlannerService()
    pools = {
        "control-plane": ([_asset("talos-cp-1", 1)], [_assignment("control-plane")]),
        "workers": ([_asset("talos-wk-0", 2)], [_assignment("worker")]),
    }
    bundle = planner.generate_bundle(
        {"name": "talos-ha", "namespace": "metal3", "control_plane_endpoint": "192.0.2.101", "os_flavor": "talos"},
        pools,
    )
    docs = planner.yaml_gen.parse_multi(bundle["cluster_config_yaml"])
    kinds = [d["kind"] for d in docs]
    assert kinds.count("TalosConfigTemplate") == 1
    assert kinds.count("MachineDeployment") == 1
    assert kinds.count("Metal3MachineTemplate") == 2  # control-plane + workers

    md = next(d for d in docs if d["kind"] == "MachineDeployment")
    # v1beta2 MachineDeployment's own contract: references use apiGroup,
    # never apiVersion -- confirmed correct here, not the mistake this
    # template's own first draft made (apiVersion, caught by this exact
    # schema check before being committed).
    assert md["spec"]["template"]["spec"]["bootstrap"]["configRef"]["apiGroup"] == "bootstrap.cluster.x-k8s.io"
    assert "apiVersion" not in md["spec"]["template"]["spec"]["bootstrap"]["configRef"]

    _assert_all_valid(docs)


def test_talos_control_plane_config_patches_are_schema_valid():
    planner = AssetPlannerService()
    pools = {"control-plane": ([_asset("talos-cp-2", 3)], [_assignment("control-plane")])}
    bundle = planner.generate_bundle(
        {
            "name": "talos-patched",
            "namespace": "metal3",
            "control_plane_endpoint": "192.0.2.102",
            "os_flavor": "talos",
            "talos_config_patches": [{"op": "add", "path": "/machine/network/hostname", "value": "cp-0"}],
        },
        pools,
    )
    docs = planner.yaml_gen.parse_multi(bundle["cluster_config_yaml"])
    kcp = next(d for d in docs if d["kind"] == "TalosControlPlane")
    patches = kcp["spec"]["controlPlaneConfig"]["controlplane"]["configPatches"]
    assert patches == [{"op": "add", "path": "/machine/network/hostname", "value": "cp-0"}]

    _assert_all_valid(docs)


def test_standard_metal3_without_os_flavor_is_unaffected():
    """The opt-in gate: a normal metal3 cluster (no os_flavor set) must
    keep rendering the standard KubeadmControlPlane-based template --
    adding Talos support must not change the default behavior for the
    project's primary, already-in-use path."""
    planner = AssetPlannerService()
    pools = {"control-plane": ([_asset("std-cp-0", 4)], [_assignment("control-plane")])}
    bundle = planner.generate_bundle(
        {"name": "standard-metal3", "namespace": "metal3", "control_plane_endpoint": "192.0.2.103"},
        pools,
    )
    docs = planner.yaml_gen.parse_multi(bundle["cluster_config_yaml"])
    kinds = [d["kind"] for d in docs]
    assert "KubeadmControlPlane" in kinds
    assert "TalosControlPlane" not in kinds
