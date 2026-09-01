import {
  Activity,
  BarChart3,
  BellRing,
  Box,
  Cable,
  Container,
  Database,
  Droplets,
  FileCheck2,
  GitBranch,
  HardDrive,
  KeyRound,
  type LucideIcon,
  MapPinned,
  Cpu,
  DoorOpen,
  Router,
  Waves,
  Waypoints,
  Network,
  Zap,
} from "lucide-react";

/**
 * One distinct Lucide icon + distinct accent color per addon, keyed by
 * the exact `name` field from backend/app/services/addon_catalog.py --
 * NOT the same navy box + 3-letter abbreviation every entry used to
 * render as. Chosen to actually mean something (Database for Ceph,
 * Zap for the GPU operator, KeyRound for the OIDC broker), not assigned
 * randomly, so a returning user starts recognizing components by shape
 * the way a real app store trains you to.
 *
 * Add a new addon to the catalog -> add its icon/color here too, or it
 * falls back to a generic Box (see AppCatalog.tsx's usage) rather than
 * crashing.
 */
export const ADDON_ICONS: Record<string, { icon: LucideIcon; color: string }> = {
  calico: { icon: Network, color: "#3b82f6" },
  "kube-ovn": { icon: Waypoints, color: "#8b5cf6" },
  multus: { icon: GitBranch, color: "#14b8a6" },
  "ovs-cni": { icon: Cable, color: "#06b6d4" },
  whereabouts: { icon: MapPinned, color: "#f97316" },
  "sriov-network-device-plugin": { icon: Cpu, color: "#6366f1" },
  "bgp-lb": { icon: Router, color: "#0ea5e9" },
  apigateway: { icon: DoorOpen, color: "#10b981" },
  ceph: { icon: Database, color: "#f43f5e" },
  "local-storage-provisioner": { icon: HardDrive, color: "#f59e0b" },
  kubevirt: { icon: Box, color: "#a855f7" },
  "nvidia-gpu-operator": { icon: Zap, color: "#22c55e" },
  "cr-registry": { icon: Container, color: "#64748b" },
  dex: { icon: KeyRound, color: "#eab308" },
  "license-manager": { icon: FileCheck2, color: "#84cc16" },
  "metrics-server": { icon: Activity, color: "#ef4444" },
  pm: { icon: BarChart3, color: "#ec4899" },
  "snmp-alert-forwarder": { icon: BellRing, color: "#fb923c" },
  "fluent-bit": { icon: Waves, color: "#0284c7" },
  fluentd: { icon: Droplets, color: "#0891b2" },
};

export const DEFAULT_ADDON_ICON: { icon: LucideIcon; color: string } = { icon: Box, color: "#64748b" };
