"""
The piece that closes the loop: HardwareAsset + NodePoolAssignment ->
rendered bmh.yaml / k8s-config.yaml(CAPI) / per-pool NIC bonding policy /
eph-net.yaml -- with zero hand-typed PCI addresses or CPU strings.

NIC role resolution: if every NIC on the asset already has a `role` set
(chosen when the asset was picked in the UI), that's used directly. If
none are set, falls back to a positional heuristic (first 2 -> control,
next 2 -> data, next 2 -> storage, rest -> sriov) and flags it so the UI
can prompt the operator to confirm/correct it.
"""
from __future__ import annotations

from typing import Any, Optional

from app.models.hardware_asset import HardwareAsset
from app.models.pool_assignment import NodePoolAssignment
from app.services.bmc import BMCService
from app.services.cpu_topology import compute_reserved_cpus, isolated_cpu_count
from app.services.yaml_generator import YamlGeneratorService

_POSITIONAL_ROLE_ORDER = ["control", "control", "data", "data", "storage", "storage"]


class AssetPlannerService:
    def __init__(
        self,
        yaml_gen: Optional[YamlGeneratorService] = None,
        bmc: Optional[BMCService] = None,
    ) -> None:
        self.yaml_gen = yaml_gen or YamlGeneratorService()
        self.bmc = bmc or BMCService()

    # ---- role resolution -------------------------------------------
    def resolve_nic_roles(self, asset: HardwareAsset, overrides: dict | None = None) -> list[dict]:
        nics = [dict(n) for n in (asset.nics or [])]
        overrides = overrides or {}
        if overrides.get("nic_roles"):
            # override shape: {pci_address_or_index: role}
            for i, nic in enumerate(nics):
                key = nic.get("pci_address") or str(i)
                if key in overrides["nic_roles"]:
                    nic["role"] = overrides["nic_roles"][key]
            return nics

        if any(n.get("role") not in (None, "unassigned") for n in nics):
            return nics

        for i, nic in enumerate(nics):
            nic["role"] = _POSITIONAL_ROLE_ORDER[i] if i < len(_POSITIONAL_ROLE_ORDER) else "sriov"
        return nics

    def resolve_disk_roles(self, asset: HardwareAsset, overrides: dict | None = None) -> list[dict]:
        disks = [dict(d) for d in (asset.disks or [])]
        overrides = overrides or {}
        if overrides.get("disk_roles"):
            for i, disk in enumerate(disks):
                key = disk.get("device") or str(i)
                if key in overrides["disk_roles"]:
                    disk["role"] = overrides["disk_roles"][key]
            return disks

        if any(d.get("role") not in (None, "unassigned") for d in disks):
            return disks

        for i, disk in enumerate(disks):
            disk["role"] = "os" if i == 0 else "ceph_osd"
        return disks

    # ---- CPU isolation -------------------------------------------
    def compute_cpu_config(self, asset: HardwareAsset, assignment: NodePoolAssignment) -> dict[str, Any]:
        reserved = compute_reserved_cpus(
            sockets=asset.cpu_sockets,
            cores_per_socket=asset.cpu_cores_per_socket,
            reserved_per_socket=assignment.reserved_cores_per_socket,
            threads_per_core=asset.cpu_threads_per_core,
        )
        isolated = isolated_cpu_count(
            sockets=asset.cpu_sockets,
            cores_per_socket=asset.cpu_cores_per_socket,
            threads_per_core=asset.cpu_threads_per_core,
            reserved_per_socket=assignment.reserved_cores_per_socket,
        )
        return {
            "reserved_cpus": reserved,
            "isolated_cpu_count": isolated,
            "cpu_manager_policy": assignment.cpu_manager_policy,
            "topology_manager_policy": assignment.topology_manager_policy,
            "isolation_interrupts": assignment.isolation_interrupts,
        }

    # ---- render inputs -------------------------------------------
    def build_bmh_host_entry(self, asset: HardwareAsset) -> dict[str, Any]:
        if not asset.bmc_address or not asset.boot_mac_address:
            raise ValueError(f"asset {asset.name} is missing bmc_address/boot_mac_address")
        return {
            "name": asset.name,
            "namespace": "metal3",
            "node_pool_name": asset.node_pool_name or "unassigned",
            "bmc_address": asset.bmc_address,
            "secret_ref": self.bmc.secret_name_for_host(asset.name),
            "boot_mac_address": asset.boot_mac_address,
            "online": False,
            "root_device_hint_model": next(
                (d.get("model") for d in (asset.disks or []) if d.get("role") == "os"), None
            ),
        }

    def build_worker_pool_entry(
        self, pool_name: str, assets: list[HardwareAsset], assignments: list[NodePoolAssignment]
    ) -> dict[str, Any]:
        """One CAPI MachineDeployment worth of config for a pool. Uses the
        first asset's CPU topology as representative for the whole pool
        (Metal3MachineTemplate/KubeadmConfigTemplate are pool-wide, not
        per-node -- warn in the UI if assets in a pool have mismatched
        topology)."""
        if not assets:
            raise ValueError(f"pool {pool_name} has no assigned assets")
        rep_asset, rep_assignment = assets[0], assignments[0]
        cpu_cfg = self.compute_cpu_config(rep_asset, rep_assignment)

        node_labels = [f"isolation-interrupts={str(rep_assignment.isolation_interrupts).lower()}"]

        # GPU labels only added if EVERY asset in the pool actually has a
        # GPU -- node_labels apply uniformly to the whole MachineDeployment
        # (CAPI has no per-node-within-a-pool label mechanism), so a mixed
        # pool can't honestly claim "gpu=true" for all its nodes. A pool
        # intended for GPU workloads should only ever contain GPU hardware
        # in the first place; this just refuses to lie about it if that
        # wasn't followed.
        if assets and all(a.gpu_count > 0 for a in assets):
            node_labels.append("gpu=true")
            if rep_asset.gpu_model:
                # K8s label values can't contain spaces -- GPU model names
                # like "NVIDIA H100 80GB" routinely do.
                safe_model = rep_asset.gpu_model.replace(" ", "_")
                node_labels.append(f"gpu-model={safe_model}")

        return {
            "name": pool_name,
            "count": len(assets),
            "node_labels": node_labels,
            "reserved_cpus": cpu_cfg["reserved_cpus"],
            "cpu_manager_policy": cpu_cfg["cpu_manager_policy"],
            "topology_manager_policy": cpu_cfg["topology_manager_policy"],
            "hugepage_type": rep_assignment.hugepage_type,
            "hugepage_count_1gb": rep_assignment.hugepage_count_1gb,
            "hugepage_count_2mb": rep_assignment.hugepage_count_2mb,
            "gpu_count_per_node": rep_asset.gpu_count if assets and all(a.gpu_count > 0 for a in assets) else 0,
        }

    def build_control_plane_fields(
        self, assets: list[HardwareAsset], assignments: list[NodePoolAssignment]
    ) -> dict[str, Any]:
        """Control-plane assets never become a MachineDeployment -- they
        drive KubeadmControlPlane.replicas and its own kubeadmConfigSpec
        directly. This is what was missing before: a pool assigned with
        role="control-plane" used to fall through to build_worker_pool_entry
        like any other pool, silently turning control-plane nodes into a
        *worker* MachineDeployment and leaving KubeadmControlPlane.replicas
        at whatever the cluster was created with (default 3) regardless of
        how much control-plane hardware was actually assigned -- which is
        exactly the failure mode for a single control-plane node: the
        deployment would sit waiting for 3 control-plane machines that were
        never going to appear."""
        if not assets:
            return {}
        rep_asset, rep_assignment = assets[0], assignments[0]
        cpu_cfg = self.compute_cpu_config(rep_asset, rep_assignment)
        return {
            "control_plane_count": len(assets),
            "control_plane_reserved_cpus": cpu_cfg["reserved_cpus"],
            "control_plane_cpu_manager_policy": cpu_cfg["cpu_manager_policy"],
            "control_plane_topology_manager_policy": cpu_cfg["topology_manager_policy"],
            "control_plane_hugepage_type": rep_assignment.hugepage_type,
            "control_plane_hugepage_count_1gb": rep_assignment.hugepage_count_1gb,
            "control_plane_hugepage_count_2mb": rep_assignment.hugepage_count_2mb,
        }

    def build_network_policy_spec(
        self, asset: HardwareAsset, overrides: dict | None = None
    ) -> dict[str, Any]:
        """Builds the `net` dict for the eph-net / node-network Jinja
        template, deriving bond membership straight from each NIC's
        resolved role."""
        nics = self.resolve_nic_roles(asset, overrides)
        by_role: dict[str, list[dict]] = {}
        for nic in nics:
            by_role.setdefault(nic.get("role", "unassigned"), []).append(nic)

        interfaces: list[dict] = []

        def _bond(name: str, members: list[dict], mode: str, mtu: int = 9000) -> None:
            if not members:
                return
            for m in members:
                interfaces.append({"name": m["pci_address"] or m.get("kernel_name"), "type": "ethernet", "state": "up", "mtu": mtu})
            interfaces.append(
                {
                    "name": name,
                    "type": "bond",
                    "state": "up",
                    "mtu": mtu,
                    "link_aggregation": {
                        "mode": mode,
                        "port": [m["pci_address"] or m.get("kernel_name") for m in members],
                    },
                }
            )

        _bond("bond_control", by_role.get("control", []), "active-backup")
        _bond("bond_data", by_role.get("data", []), "802.3ad")
        _bond("bond_storage", by_role.get("storage", []), "802.3ad")

        for nic in by_role.get("sriov", []):
            interfaces.append(
                {
                    "name": nic["pci_address"] or nic.get("kernel_name"),
                    "type": "ethernet",
                    "state": "up",
                    "mtu": nic.get("mtu", 3040),
                }
            )

        return {"interfaces": interfaces, "routes": []}

    # ---- top-level: generate everything for a cluster -------------
    def generate_bundle(
        self,
        cluster_spec: dict[str, Any],
        pools: dict[str, tuple[list[HardwareAsset], list[NodePoolAssignment]]],
        eph_asset: Optional[HardwareAsset] = None,
    ) -> dict[str, Any]:
        all_assets = [a for assets, _ in pools.values() for a in assets]
        bmh_hosts = [self.build_bmh_host_entry(a) for a in all_assets]
        bmh_yaml = self.yaml_gen.render_bmh(bmh_hosts)

        # Split by role BEFORE rendering: a pool's role is a property of the
        # assignment (every assignment in a pool shares the same role --
        # enforced by how /pools/{pool}/assign works, one call per pool),
        # not of the pool name itself.
        control_plane_pools = {
            name: (assets, assignments)
            for name, (assets, assignments) in pools.items()
            if assignments and assignments[0].role == "control-plane"
        }
        worker_pools_only = {
            name: (assets, assignments)
            for name, (assets, assignments) in pools.items()
            if name not in control_plane_pools
        }

        control_plane_assets = [a for assets, _ in control_plane_pools.values() for a in assets]
        control_plane_assignments = [
            x for _, assignments in control_plane_pools.values() for x in assignments
        ]
        control_plane_fields = self.build_control_plane_fields(control_plane_assets, control_plane_assignments)

        worker_pools = [
            self.build_worker_pool_entry(name, assets, assignments)
            for name, (assets, assignments) in worker_pools_only.items()
        ]
        total_worker_count = sum(len(assets) for assets, _ in worker_pools_only.values())

        # A cluster is a genuine single-node target -- one control-plane
        # node, nothing else -- when there's exactly one control-plane
        # asset and no worker hardware at all. In that case the control
        # plane also has to run workloads, so its NoSchedule taint needs
        # removing; an explicit `allow_workloads_on_control_plane` in the
        # caller's cluster_spec always wins over this inference.
        single_node = len(control_plane_assets) == 1 and total_worker_count == 0
        allow_workloads_on_control_plane = cluster_spec.get(
            "allow_workloads_on_control_plane", single_node
        )

        merged_cluster_spec: dict[str, Any] = {
            **cluster_spec,
            **control_plane_fields,
            "worker_pools": worker_pools,
            "allow_workloads_on_control_plane": allow_workloads_on_control_plane,
            "hosts": [{"name": a.name} for a in all_assets],
        }

        cluster_config_yaml = self.yaml_gen.render_cluster_config(merged_cluster_spec)

        network_policies = {}
        for pool_name, (assets, _assignments) in pools.items():
            for asset in assets:
                net = self.build_network_policy_spec(asset)
                network_policies[f"{pool_name}/{asset.name}"] = self.yaml_gen.render_ephemeral_network(net)

        eph_net_yaml = None
        if eph_asset is not None:
            eph_net_yaml = self.yaml_gen.render_ephemeral_network(
                self.build_network_policy_spec(eph_asset)
            )

        return {
            "bmh_yaml": bmh_yaml,
            "cluster_config_yaml": cluster_config_yaml,
            "network_policies": network_policies,
            "eph_net_yaml": eph_net_yaml,
            # Reusable by the deployment trigger so it applies exactly what
            # was previewed here instead of re-deriving it differently.
            "cluster_spec": merged_cluster_spec,
        }
