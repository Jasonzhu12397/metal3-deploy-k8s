// Mirrors backend/app/schemas/*.py field-for-field. Keep these two in sync
// by hand -- there's no shared schema generator wired up yet (a natural
// follow-up would be exporting an OpenAPI-generated client instead).

export type ClusterStatus =
  | "pending" | "bootstrapping" | "provisioning" | "ready" | "failed" | "deleting";

export type InfrastructureProvider = "metal3" | "openstack" | "vsphere" | "kubevirt";

export interface Cluster {
  id: string;
  name: string;
  namespace: string;
  status: ClusterStatus;
  infrastructure_provider: InfrastructureProvider;
  control_plane_endpoint: string | null;
  control_plane_count: number;
  worker_pool_config: { pools?: WorkerPoolSpec[] };
  spec: Record<string, unknown>;
}

export interface WorkerPoolSpec {
  name: string;
  count: number;
  role?: string;
  node_labels?: string[];
  // Cloud-provider pools only (infrastructure_provider != "metal3")
  flavor?: string;
  image?: string;
}

export interface ClusterCreate {
  name: string;
  namespace?: string;
  infrastructure_provider?: InfrastructureProvider;
  control_plane_count?: number;
  control_plane_endpoint?: string | null;
  control_plane_flavor?: string;
  control_plane_image?: string;
  worker_pools?: WorkerPoolSpec[];
  spec?: Record<string, unknown>;
}

export type BMHState =
  | "unknown" | "registering" | "inspecting" | "available"
  | "provisioning" | "provisioned" | "deprovisioning" | "error";

export interface BareMetalHostCreate {
  name: string;
  node_pool_name: string;
  bmc_address: string;
  boot_mac_address: string;
  credentials: { username: string; password: string };
  online?: boolean;
  disable_certificate_verification?: boolean;
  root_device_hint_model?: string | null;
}

export type AssetStatus = "discovered" | "available" | "reserved" | "provisioned" | "decommissioned";
export type NicRole = "control" | "data" | "storage" | "sriov" | "unassigned";
export type DiskRole = "os" | "ceph_osd" | "ceph_journal" | "local_storage" | "unassigned";

export interface NicSpec {
  pci_address: string;
  kernel_name?: string | null;
  model?: string | null;
  speed_gbps?: number | null;
  numa_node?: number | null;
  mtu?: number;
  sriov_capable?: boolean;
  total_vfs?: number;
  role: NicRole;
}

export interface DiskSpec {
  device?: string | null;
  model?: string | null;
  size_gb?: number | null;
  media_type?: string;
  role: DiskRole;
}

export interface HardwareAsset {
  id: string;
  name: string;
  serial_number: string | null;
  vendor: string | null;
  model: string | null;
  status: AssetStatus;
  cpu_model: string | null;
  cpu_sockets: number;
  cpu_cores_per_socket: number;
  cpu_threads_per_core: number;
  memory_gb: number;
  nics: NicSpec[];
  disks: DiskSpec[];
  bmc_address: string | null;
  boot_mac_address: string | null;
  node_pool_name: string | null;
  cluster_id: string | null;
}

export interface PoolAssignRequest {
  asset_ids: string[];
  role?: "worker" | "control-plane";
  reserved_cores_per_socket?: number;
  cpu_manager_policy?: string;
  topology_manager_policy?: string;
  isolation_interrupts?: boolean;
  hugepage_type?: string;
  hugepage_count_1gb?: number;
  hugepage_count_2mb?: number;
}

export interface PoolAssignment {
  id: string;
  cluster_id: string;
  pool_name: string;
  asset_id: string;
  role: string;
  reserved_cores_per_socket: number;
  cpu_manager_policy: string;
  topology_manager_policy: string;
  isolation_interrupts: boolean;
  hugepage_type: string;
  hugepage_count_1gb: number;
  hugepage_count_2mb: number;
  computed_reserved_cpus: string;
  computed_isolated_cpu_count: number;
}

export interface ClusterManifestBundle {
  bmh_yaml: string;
  cluster_config_yaml: string;
  network_policies: Record<string, string>;
  eph_net_yaml: string | null;
}

export type DeploymentPhase =
  | "queued" | "generating_manifests" | "bootstrapping_ephemeral_node" | "applying_bmh"
  | "waiting_for_hosts" | "applying_cluster" | "waiting_for_control_plane"
  | "installing_addons" | "complete" | "failed";

export interface Deployment {
  id: string;
  cluster_id: string;
  phase: DeploymentPhase;
  celery_task_id: string | null;
  error_message: string | null;
}

export interface DeploymentProgressEvent {
  phase: string;
  message: string;
}

export interface AddonCatalogItem {
  name: string;
  display_name: string;
  category: string;
  description: string;
  icon: string;
  enabled: boolean;
}

export interface AddonToggleResult {
  cluster_id: string;
  name: string;
  enabled: boolean;
}
