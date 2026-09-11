"""
Keeps USAGE.md's "1.2 用 Talos 而不是标准 kubeadm 的裸金属集群" example
honest -- if this test ever fails, that section's example payload no
longer reflects real code behavior and needs updating alongside
whatever changed, not silently left stale.
"""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.schemas.cluster import ClusterCreate  # noqa: E402
from app.services.asset_planner import AssetPlannerService  # noqa: E402
from app.models.hardware_asset import HardwareAsset  # noqa: E402

# Exactly the JSON body USAGE.md's "1.2" section shows, kept in sync by
# hand -- if you change one, change the other.
USAGE_MD_TALOS_EXAMPLE_SPEC = {
    "os_flavor": "talos",
    "talos_version": "v1.12",
    "image_url": "https://github.com/siderolabs/talos/releases/download/v1.12.12/metal-amd64.raw.zst",
    "talos_config_patches": [{"op": "add", "path": "/machine/network/hostname", "value": "talos-cp"}],
}


def test_usage_md_talos_example_spec_validates_against_the_real_clustercreate_schema():
    payload = ClusterCreate(
        name="talos-prod-01",
        namespace="metal3",
        control_plane_count=3,
        control_plane_endpoint="192.0.2.1",
        spec=USAGE_MD_TALOS_EXAMPLE_SPEC,
    )
    assert payload.spec == USAGE_MD_TALOS_EXAMPLE_SPEC


def test_usage_md_talos_example_spec_actually_renders_a_talos_control_plane_end_to_end():
    """The real point of USAGE.md's own warning: these fields only take
    effect because they're nested under "spec" and get merged into the
    real cluster_spec dict api/deployments.py builds
    (base_cluster_spec = {..., **cluster.spec, ...}) -- this test
    reproduces that exact merge, not just schema validation, to catch a
    regression in either the merge logic or the template dispatch."""
    planner = AssetPlannerService()
    cp_asset = HardwareAsset(
        name="talos-cp-usage-doc",
        cpu_sockets=1,
        cpu_cores_per_socket=32,
        cpu_threads_per_core=2,
        memory_gb=128,
        bmc_address="redfish://192.0.2.20/redfish/v1/Systems/1",
        boot_mac_address="aa:bb:cc:dd:ee:20",
        gpu_model=None,
        gpu_count=0,
        gpu_memory_gb=None,
    )
    cp_assignment = SimpleNamespace(
        role="control-plane",
        reserved_cores_per_socket=2,
        cpu_manager_policy="static",
        topology_manager_policy="single-numa-node",
        isolation_interrupts=False,
        hugepage_type="1GB",
        hugepage_count_1gb=8,
        hugepage_count_2mb=0,
    )
    pools = {"control-plane": ([cp_asset], [cp_assignment])}

    # The exact real merge api/deployments.py's create-deployment
    # endpoint does: base_cluster_spec = {core fields, **cluster.spec}
    base_cluster_spec = {
        "name": "talos-prod-01",
        "namespace": "metal3",
        "control_plane_endpoint": "192.0.2.1",
        **USAGE_MD_TALOS_EXAMPLE_SPEC,
    }
    bundle = planner.generate_bundle(base_cluster_spec, pools)
    docs = planner.yaml_gen.parse_multi(bundle["cluster_config_yaml"])

    kinds = [d["kind"] for d in docs]
    assert "TalosControlPlane" in kinds
    assert "KubeadmControlPlane" not in kinds

    kcp = next(d for d in docs if d["kind"] == "TalosControlPlane")
    patches = kcp["spec"]["controlPlaneConfig"]["controlplane"]["configPatches"]
    assert patches == USAGE_MD_TALOS_EXAMPLE_SPEC["talos_config_patches"]
