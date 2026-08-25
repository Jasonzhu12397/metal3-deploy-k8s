"""
Static catalog of the addons this platform knows how to install on a
target cluster -- the "app store" catalog. Mirrors the addon set already
used in the operator's existing ccdadm-config.yaml (`addons:` section) so
switching to this platform doesn't lose any of them; add new entries here
as new addons are supported.

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
    {"name": "ecfe", "display_name": "ECFE (BGP Speaker)", "category": "networking",
     "description": "BGP/BFD-based external LoadBalancer IP announcement (OAM/signalling/LI pools).",
     "icon": "ECF"},
    {"name": "apigateway", "display_name": "Gateway API", "category": "networking",
     "description": "Kubernetes Gateway API implementation, exposing north-south HTTP/gRPC routes. Replaces the older Ingress-based setup (ingress-nginx) -- Ingress is now deprecated in favor of Gateway API's HTTPRoute/Gateway resources.",
     "icon": "APG"},
    {"name": "ceph", "display_name": "Ceph (Rook)", "category": "storage",
     "description": "Hosted block/file storage backed by NVMe OSDs on the storage-role disks.",
     "icon": "CPH"},
    {"name": "local-storage-provisioner", "display_name": "Local Storage Provisioner", "category": "storage",
     "description": "Local-disk StorageClass for pools that don't run Ceph OSDs.",
     "icon": "LSP"},
    {"name": "cr-registry", "display_name": "Container Registry", "category": "platform",
     "description": "In-cluster OCI registry backed by the CephFS storage class.",
     "icon": "REG"},
    {"name": "dex", "display_name": "Dex (OIDC)", "category": "platform",
     "description": "OIDC identity broker; wires kubectl/console auth to an LDAP backend.",
     "icon": "DEX"},
    {"name": "ccd-licensing", "display_name": "Licensing", "category": "platform",
     "description": "NELS license-server integration.",
     "icon": "LIC"},
    {"name": "metrics-server", "display_name": "Metrics Server", "category": "observability",
     "description": "Resource metrics API backing `kubectl top` and HPA.",
     "icon": "MTR"},
    {"name": "pm", "display_name": "Prometheus Monitoring", "category": "observability",
     "description": "VictoriaMetrics-based metrics stack + Alertmanager, exposed via the Gateway API.",
     "icon": "PM"},
    {"name": "pm_webhook_snmp", "display_name": "SNMP Alert Forwarder", "category": "observability",
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
