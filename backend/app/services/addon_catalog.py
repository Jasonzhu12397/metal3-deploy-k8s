"""
Static catalog of the addons this platform knows how to install on a
target cluster -- the "app store" catalog. Covers the common CNI/
storage/observability/platform addon set a typical telco-grade bare-metal
Kubernetes deployment needs; add new entries here as new addons are
supported.

Actually installing an addon (Helm/kubectl apply) is still the extension
point noted in `tasks/deployment_tasks.py` (`installing_addons` phase) --
this catalog + the enable/disable endpoints just track *intent* (which
addons should be on for a given cluster) so the UI has something real to
drive and the deployment task has something real to read.
"""
from __future__ import annotations

from typing import TypedDict


class AddonCatalogEntry(TypedDict):
    name: str
    display_name: str
    category: str
    description: str
    icon: str  # short glyph label used by the UI in lieu of a real icon asset


ADDON_CATALOG: list[AddonCatalogEntry] = [
    {"name": "calico", "display_name": "Calico", "category": "networking",
     "description": "Pod/service network CNI (IPv4, no IPIP, tuned MTU for the data-fabric bond).",
     "icon": "CAL"},
    {"name": "kube-ovn", "display_name": "Kube-OVN", "category": "networking",
     "description": "OVN/OVS-based CNI -- alternative to Calico when you need subnet-per-namespace, static pod IPs, or a distributed gateway/east-west policy model. Pick one CNI, not both.",
     "icon": "KOV"},
    {"name": "multus", "display_name": "Multus CNI", "category": "networking",
     "description": "Attach multiple network interfaces to pods (needed alongside SR-IOV/OVS pools).",
     "icon": "MLT"},
    {"name": "ovs-cni", "display_name": "OVS CNI", "category": "networking",
     "description": "Open vSwitch bridge attachment for pods on the data-fabric bond.",
     "icon": "OVS"},
    {"name": "whereabouts", "display_name": "Whereabouts", "category": "networking",
     "description": "Cluster-wide IPAM for Multus secondary networks.",
     "icon": "WHB"},
    {"name": "sriov-network-device-plugin", "display_name": "SR-IOV Device Plugin", "category": "networking",
     "description": "Exposes SR-IOV VFs on high-throughput pools as schedulable device resources.",
     "icon": "SRI"},
    {"name": "bgp-lb", "display_name": "MetalLB (FRR-K8s backend)", "category": "networking",
     "description": "BGP/BFD-based external LoadBalancer IP announcement for service VIPs, via MetalLB running its FRR-K8s backend (the current recommended default -- MetalLB's older native Go BGP speaker and the plain FRR-sidecar mode are both deprecated). Lets external routers learn a service's VIP as a route instead of relying on ARP/L2, so VIPs can be spread across multiple upstream network segments.",
     "icon": "BGP"},
    {"name": "apigateway", "display_name": "Gateway API", "category": "networking",
     "description": "Kubernetes Gateway API implementation, exposing north-south HTTP/gRPC routes. Replaces the older Ingress-based setup (ingress-nginx) -- Ingress is now deprecated in favor of Gateway API's HTTPRoute/Gateway resources.",
     "icon": "APG"},
    {"name": "ceph", "display_name": "Ceph (Rook)", "category": "storage",
     "description": "Hosted block/file storage backed by NVMe OSDs on the storage-role disks.",
     "icon": "CPH"},
    {"name": "local-storage-provisioner", "display_name": "Local Storage Provisioner", "category": "storage",
     "description": "Local-disk StorageClass for pools that don't run Ceph OSDs.",
     "icon": "LSP"},
    {"name": "kubevirt", "display_name": "KubeVirt", "category": "platform",
     "description": "Run traditional VMs as Kubernetes-managed workloads (VirtualMachine/VirtualMachineInstance CRDs) alongside containers on the same cluster -- for legacy/VM-only workloads that can't be containerized yet. Also what backs this platform's own KVM-target Cluster API provider (CAPK) when 'kubevirt' is picked as the target cluster's infrastructure_provider.",
     "icon": "KV"},
    {"name": "nvidia-gpu-operator", "display_name": "NVIDIA GPU Operator", "category": "compute",
     "description": "Installs and manages NVIDIA drivers, the container toolkit, and the device plugin on nodes with a GPU -- once running, nodes with real GPU hardware automatically advertise a schedulable `nvidia.com/gpu` resource, and pods request it the normal Kubernetes way (resources.limits). Only makes sense to enable on a cluster that actually has GPU-bearing hardware assigned to at least one pool (see the 'GPU' filter on the hardware assets page) -- installing it on GPU-less nodes does nothing harmful, just nothing useful either.",
     "icon": "GPU"},
    {"name": "cr-registry", "display_name": "Container Registry", "category": "platform",
     "description": "In-cluster OCI registry backed by the CephFS storage class.",
     "icon": "REG"},
    {"name": "dex", "display_name": "Dex (OIDC)", "category": "platform",
     "description": "OIDC identity broker; wires kubectl/console auth to an LDAP backend.",
     "icon": "DEX"},
    {"name": "license-manager", "display_name": "Licensing", "category": "platform",
     "description": "Central license-server integration for cluster entitlement/capacity validation.",
     "icon": "LIC"},
    {"name": "metrics-server", "display_name": "Metrics Server", "category": "observability",
     "description": "Resource metrics API backing `kubectl top` and HPA.",
     "icon": "MTR"},
    {"name": "pm", "display_name": "Prometheus Monitoring", "category": "observability",
     "description": "VictoriaMetrics-based metrics stack + Alertmanager, exposed via the Gateway API.",
     "icon": "PM"},
    {"name": "snmp-alert-forwarder", "display_name": "SNMP Alert Forwarder", "category": "observability",
     "description": "Forwards Alertmanager webhooks as SNMP traps to an external NMS.",
     "icon": "SNM"},
    {"name": "fluent-bit", "display_name": "Fluent Bit", "category": "observability",
     "description": "Node-level log collector, forwards to Fluentd.",
     "icon": "FLB"},
    {"name": "fluentd", "display_name": "Fluentd", "category": "observability",
     "description": "Aggregates and ships cluster logs to an external syslog/TLS receiver.",
     "icon": "FLD"},
]

ADDON_BY_NAME = {a["name"]: a for a in ADDON_CATALOG}
