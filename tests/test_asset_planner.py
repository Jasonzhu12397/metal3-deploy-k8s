"""
Exercises the hardware-asset -> rendered-YAML pipeline end to end without
a live cluster or database: reserved-CPU math, NIC role resolution, and
full bundle generation from picked hardware.
"""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.services.cpu_topology import compute_reserved_cpus, isolated_cpu_count  # noqa: E402
from app.services.asset_planner import AssetPlannerService  # noqa: E402


def _arg_value(kubelet_extra_args: list[dict], name: str) -> str:
    """kubeletExtraArgs is a list of {name, value} objects (CAPI v1beta2
    contract), not a map -- see templates/capi/cluster-template.yaml.j2's
    header comment for why. Looks up one arg's value by name."""
    return next(item["value"] for item in kubelet_extra_args if item["name"] == name)


def test_compute_reserved_cpus_matches_known_pattern():
    # 2 sockets x 32 cores, reserve 4 cores/socket, SMT=2 -> matches the
    # reserved_cpus string used in the operator's existing control-plane pool.
    result = compute_reserved_cpus(sockets=2, cores_per_socket=32, reserved_per_socket=4, threads_per_core=2)
    assert result == "0,64,1,65,2,66,3,67,32,96,33,97,34,98,35,99"


def test_isolated_cpu_count():
    # 2x32x2 = 128 logical; reserve 4/socket*2 sockets*2 threads = 16 reserved
    assert isolated_cpu_count(sockets=2, cores_per_socket=32, threads_per_core=2, reserved_per_socket=4) == 112


def _asset(**kw):
    defaults = dict(
        name="worker-node-01",
        cpu_sockets=2,
        cpu_cores_per_socket=32,
        cpu_threads_per_core=2,
        bmc_address="redfish://192.0.2.10/redfish/v1/Systems/1",
        boot_mac_address="aa:bb:cc:dd:ee:01",
        node_pool_name="pool1",
        gpu_model=None,
        gpu_count=0,
        gpu_memory_gb=None,
        nics=[
            {"pci_address": "0000:02:00.0", "role": "control"},
            {"pci_address": "0000:02:00.1", "role": "control"},
            {"pci_address": "0000:37:00.0", "role": "data"},
            {"pci_address": "0000:37:00.1", "role": "data"},
        ],
        disks=[
            {"model": "Dell BOSS-N1", "role": "os"},
            {"model": "Dell Ent NVMe CM7 U.2 3.2TB", "role": "ceph_osd"},
        ],
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def _assignment(**kw):
    defaults = dict(
        role="worker",
        reserved_cores_per_socket=4,
        cpu_manager_policy="static",
        topology_manager_policy="single-numa-node",
        isolation_interrupts=False,
        hugepage_type="1GB",
        hugepage_count_1gb=16,
        hugepage_count_2mb=0,
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def test_build_bmh_host_entry_uses_os_disk_as_root_hint():
    planner = AssetPlannerService()
    asset = _asset()
    entry = planner.build_bmh_host_entry(asset)
    assert entry["root_device_hint_model"] == "Dell BOSS-N1"
    assert entry["bmc_address"] == asset.bmc_address
    assert entry["secret_ref"] == "worker-node-01-bmc-secret"


def test_network_policy_groups_nics_by_role_into_bonds():
    planner = AssetPlannerService()
    asset = _asset()
    net = planner.build_network_policy_spec(asset)
    names = [i["name"] for i in net["interfaces"]]
    assert "bond_control" in names
    assert "bond_data" in names
    bond_control = next(i for i in net["interfaces"] if i["name"] == "bond_control")
    assert bond_control["link_aggregation"]["mode"] == "active-backup"
    assert bond_control["link_aggregation"]["port"] == ["0000:02:00.0", "0000:02:00.1"]


def test_generate_bundle_produces_valid_yaml_for_picked_hardware():
    planner = AssetPlannerService()
    asset = _asset()
    assignment = _assignment()
    pools = {"pool1": ([asset], [assignment])}
    cluster_spec = {
        "name": "prod-cluster-01",
        "namespace": "metal3",
        "control_plane_count": 3,
        "control_plane_endpoint": "192.0.2.1",
    }
    bundle = planner.generate_bundle(cluster_spec, pools)

    bmh_docs = planner.yaml_gen.parse_multi(bundle["bmh_yaml"])
    assert bmh_docs[0]["kind"] == "BareMetalHost"
    assert bmh_docs[0]["spec"]["rootDeviceHints"]["model"] == "Dell BOSS-N1"

    cluster_docs = planner.yaml_gen.parse_multi(bundle["cluster_config_yaml"])
    kct = next(d for d in cluster_docs if d["kind"] == "KubeadmConfigTemplate")
    kubelet_args = kct["spec"]["template"]["spec"]["joinConfiguration"]["nodeRegistration"]["kubeletExtraArgs"]
    assert _arg_value(kubelet_args, "reserved-cpus") == "0,64,1,65,2,66,3,67,32,96,33,97,34,98,35,99"

    assert "pool1/worker-node-01" in bundle["network_policies"]


def test_control_plane_pool_drives_kubeadmcontrolplane_not_a_machinedeployment():
    """This is the core single-node-deploy bug: assigning hardware with
    role="control-plane" must set KubeadmControlPlane.replicas and must
    NOT turn into a worker MachineDeployment."""
    planner = AssetPlannerService()
    cp_asset = _asset(name="cp-01", node_pool_name="control-plane")
    cp_assignment = _assignment(role="control-plane", reserved_cores_per_socket=2)
    pools = {"control-plane": ([cp_asset], [cp_assignment])}
    cluster_spec = {
        "name": "single-node-demo",
        "namespace": "metal3",
        "control_plane_count": 3,  # stale/default value from cluster creation -- must be overridden
        "control_plane_endpoint": "10.0.0.10",
    }

    bundle = planner.generate_bundle(cluster_spec, pools)
    docs = planner.yaml_gen.parse_multi(bundle["cluster_config_yaml"])
    kinds = [d["kind"] for d in docs]

    assert "MachineDeployment" not in kinds
    assert "KubeadmConfigTemplate" not in kinds

    kcp = next(d for d in docs if d["kind"] == "KubeadmControlPlane")
    assert kcp["spec"]["replicas"] == 1  # not the stale 3

    kubelet_args = kcp["spec"]["kubeadmConfigSpec"]["initConfiguration"]["nodeRegistration"]["kubeletExtraArgs"]
    assert _arg_value(kubelet_args, "reserved-cpus") == compute_reserved_cpus(2, 32, 2, 2)

    # single control-plane node, zero workers -> genuine single-node cluster
    # -> the control-plane NoSchedule taint must be dropped so pods can run.
    assert "postKubeadmCommands" in kcp["spec"]["kubeadmConfigSpec"]
    assert "taint node" in kcp["spec"]["kubeadmConfigSpec"]["postKubeadmCommands"][0]

    assert bundle["cluster_spec"]["control_plane_count"] == 1
    assert bundle["cluster_spec"]["allow_workloads_on_control_plane"] is True
    assert bundle["cluster_spec"]["hosts"] == [{"name": "cp-01"}]


def test_control_plane_plus_workers_does_not_untaint():
    """Same control-plane-pool handling, but with worker hardware also
    assigned -- this is a normal HA-ish cluster, not a single-node one, so
    the control-plane taint should stay unless the caller explicitly opts
    in via allow_workloads_on_control_plane."""
    planner = AssetPlannerService()
    cp_asset = _asset(name="cp-01")
    cp_assignment = _assignment(role="control-plane")
    worker_asset = _asset(name="worker-01")
    worker_assignment = _assignment(role="worker")
    pools = {
        "control-plane": ([cp_asset], [cp_assignment]),
        "pool1": ([worker_asset], [worker_assignment]),
    }
    cluster_spec = {"name": "ha-demo", "namespace": "metal3", "control_plane_endpoint": "10.0.0.10"}

    bundle = planner.generate_bundle(cluster_spec, pools)
    assert bundle["cluster_spec"]["control_plane_count"] == 1
    assert bundle["cluster_spec"]["allow_workloads_on_control_plane"] is False

    docs = planner.yaml_gen.parse_multi(bundle["cluster_config_yaml"])
    kcp = next(d for d in docs if d["kind"] == "KubeadmControlPlane")
    assert "postKubeadmCommands" not in kcp["spec"]["kubeadmConfigSpec"]
    kinds = [d["kind"] for d in docs]
    assert kinds.count("MachineDeployment") == 1  # only the real worker pool
