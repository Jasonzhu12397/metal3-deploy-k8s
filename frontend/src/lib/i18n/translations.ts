/**
 * Translation coverage so far: the global chrome (Sidebar + Topbar, seen
 * on every page) and the App Store page (which this dictionary was
 * built for, alongside its app-store redesign). Every OTHER page
 * (clusters, hardware assets, deployments, hosts, LLM providers, AI
 * workloads...) is still hardcoded Chinese -- this is deliberately
 * scoped, not a claim that the whole app is translated. `zh` is the
 * source of truth for the key set; `en` is typed as Record<TranslationKey,
 * string> so TypeScript itself catches a missing translation at compile
 * time rather than silently falling back at runtime.
 */
export const translations = {
  zh: {
    // App shell
    "app.name": "Metal3 控制台",

    // Sidebar
    "nav.overview": "概览",
    "nav.clusters": "集群管理",
    "nav.hardwareAssets": "硬件资产",
    "nav.baremetalHosts": "裸金属主机",
    "nav.deployments": "部署任务",
    "nav.appCatalog": "应用商店",
    "nav.llmProviders": "LLM 凭证",
    "nav.aiWorkloads": "AI 工作负载",
    "sidebar.tagline": "裸金属 & K8s",

    // Topbar
    "topbar.title.detail": "详情",
    "topbar.apiOnline": "在线",
    "topbar.apiOffline": "离线",
    "topbar.refresh": "刷新",
    "topbar.logout": "退出登录",
    "topbar.language": "语言",
    "lang.toggle": "EN",

    // App Store
    "catalog.title": "应用商店",
    "catalog.subtitle": "这套平台常用的组件目录，对应集群配置里的 addons 段。选一个集群可以直接在这里启用/停用。",
    "catalog.search": "搜索组件名称或描述...",
    "catalog.allCategories": "全部分类",
    "catalog.selectClusterPlaceholder": "仅浏览目录（不关联集群）",
    "catalog.installed": "已启用",
    "catalog.notInstalled": "未配置",
    "catalog.install": "启用",
    "catalog.uninstall": "停用",
    "catalog.loading": "加载中...",
    "catalog.empty": "没有匹配的组件",
    "catalog.emptyHint": "换个搜索词，或者切换分类试试",
    "catalog.resultsCount": "共 {count} 个组件",
    "catalog.category.networking": "网络",
    "catalog.category.storage": "存储",
    "catalog.category.platform": "平台",
    "catalog.category.observability": "可观测性",
    "catalog.category.compute": "计算",

    // Addon catalog entries -- name matches backend addon_catalog.py's
    // `name` field exactly, description translated from that same file
    // (not re-worded independently, so the two never drift apart).
    "addon.calico.name": "Calico",
    "addon.calico.desc": "Pod/Service 网络 CNI（IPv4，不启用 IPIP，MTU 针对数据面 bond 调优）。",
    "addon.kube-ovn.name": "Kube-OVN",
    "addon.kube-ovn.desc": "基于 OVN/OVS 的 CNI——需要按命名空间划子网、固定 Pod IP、或分布式网关/东西向策略模型时可替代 Calico。二选一，不要同时装。",
    "addon.multus.name": "Multus CNI",
    "addon.multus.desc": "给 Pod 挂多张网卡（配合 SR-IOV/OVS 池使用）。",
    "addon.ovs-cni.name": "OVS CNI",
    "addon.ovs-cni.desc": "把数据面 bond 上的 Open vSwitch 网桥挂给 Pod。",
    "addon.whereabouts.name": "Whereabouts",
    "addon.whereabouts.desc": "给 Multus 的第二网络做集群级 IPAM 地址分配。",
    "addon.sriov-network-device-plugin.name": "SR-IOV 设备插件",
    "addon.sriov-network-device-plugin.desc": "把高吞吐节点池上的 SR-IOV 虚拟功能（VF）暴露成可调度的设备资源。",
    "addon.bgp-lb.name": "MetalLB（FRR-K8s 后端）",
    "addon.bgp-lb.desc": "基于 BGP/BFD 给 Service 的 LoadBalancer IP 做外部宣告，走 MetalLB 的 FRR-K8s 后端（目前官方推荐的默认项——原生 Go BGP 实现和纯 FRR sidecar 模式都已弃用）。让外部路由器把 Service VIP 当路由学习，而不是靠 ARP/二层，VIP 可以分散到多个上联网段。",
    "addon.apigateway.name": "Gateway API",
    "addon.apigateway.desc": "Kubernetes Gateway API 实现，负责南北向 HTTP/gRPC 路由。替代旧的 Ingress 方案（ingress-nginx）——Ingress 已弃用，官方转向 Gateway API 的 HTTPRoute/Gateway 资源。",
    "addon.ceph.name": "Ceph（Rook）",
    "addon.ceph.desc": "基于存储角色磁盘上的 NVMe OSD，提供托管块/文件存储。",
    "addon.local-storage-provisioner.name": "本地存储驱动",
    "addon.local-storage-provisioner.desc": "给没有跑 Ceph OSD 的节点池提供本地磁盘 StorageClass。",
    "addon.kubevirt.name": "KubeVirt",
    "addon.kubevirt.desc": "把传统虚拟机作为 Kubernetes 管理的工作负载运行（VirtualMachine/VirtualMachineInstance CRD），跟容器跑在同一个集群里——用于还没法容器化的遗留/纯 VM 负载。目标集群的 infrastructure_provider 选 kubevirt 时，这也是背后那套 KVM Cluster API provider（CAPK）的基础。",
    "addon.nvidia-gpu-operator.name": "NVIDIA GPU Operator",
    "addon.nvidia-gpu-operator.desc": "在带 GPU 的节点上自动装好 NVIDIA 驱动、容器工具链和设备插件——装好之后，带真实 GPU 硬件的节点会自动暴露可调度的 nvidia.com/gpu 资源，Pod 按标准方式（resources.limits）申请即可。只有集群里真的分配了 GPU 硬件（硬件资产页面「仅 GPU」筛选）才有意义装这个。",
    "addon.cr-registry.name": "容器镜像仓库",
    "addon.cr-registry.desc": "基于 CephFS 存储类的集群内 OCI 镜像仓库。",
    "addon.dex.name": "Dex（OIDC）",
    "addon.dex.desc": "OIDC 身份代理，把 kubectl/控制台鉴权接到 LDAP 后端。",
    "addon.license-manager.name": "License 管理",
    "addon.license-manager.desc": "对接中心化 License 服务器，做集群授权/容量校验。",
    "addon.metrics-server.name": "Metrics Server",
    "addon.metrics-server.desc": "资源指标 API，支撑 kubectl top 和 HPA。",
    "addon.pm.name": "Prometheus 监控",
    "addon.pm.desc": "基于 VictoriaMetrics 的指标栈 + Alertmanager，通过 Gateway API 对外暴露。",
    "addon.snmp-alert-forwarder.name": "SNMP 告警转发",
    "addon.snmp-alert-forwarder.desc": "把 Alertmanager 的 Webhook 告警转发成 SNMP trap，对接外部网管系统。",
    "addon.fluent-bit.name": "Fluent Bit",
    "addon.fluent-bit.desc": "节点级日志采集器，转发给 Fluentd。",
    "addon.fluentd.name": "Fluentd",
    "addon.fluentd.desc": "聚合并把集群日志推送到外部 syslog/TLS 接收端。",
  },
  en: {
    // App shell
    "app.name": "Metal3 Console",

    // Sidebar
    "nav.overview": "Overview",
    "nav.clusters": "Clusters",
    "nav.hardwareAssets": "Hardware Assets",
    "nav.baremetalHosts": "Bare Metal Hosts",
    "nav.deployments": "Deployments",
    "nav.appCatalog": "App Store",
    "nav.llmProviders": "LLM Credentials",
    "nav.aiWorkloads": "AI Workloads",
    "sidebar.tagline": "Bare Metal & K8s",

    // Topbar
    "topbar.title.detail": "Detail",
    "topbar.apiOnline": "Online",
    "topbar.apiOffline": "Offline",
    "topbar.refresh": "Refresh",
    "topbar.logout": "Log out",
    "topbar.language": "Language",
    "lang.toggle": "中文",

    // App Store
    "catalog.title": "App Store",
    "catalog.subtitle": "The catalog of addons this platform supports, matching the addons: section of a cluster's config. Pick a cluster to enable/disable them directly here.",
    "catalog.search": "Search by name or description...",
    "catalog.allCategories": "All categories",
    "catalog.selectClusterPlaceholder": "Browse catalog only (no cluster selected)",
    "catalog.installed": "Enabled",
    "catalog.notInstalled": "Not configured",
    "catalog.install": "Enable",
    "catalog.uninstall": "Disable",
    "catalog.loading": "Loading...",
    "catalog.empty": "No matching addons",
    "catalog.emptyHint": "Try a different search term or category",
    "catalog.resultsCount": "{count} addons",
    "catalog.category.networking": "Networking",
    "catalog.category.storage": "Storage",
    "catalog.category.platform": "Platform",
    "catalog.category.observability": "Observability",
    "catalog.category.compute": "Compute",

    // Addon catalog entries -- descriptions copied verbatim from
    // backend/app/services/addon_catalog.py (the source of truth for
    // what each addon actually does), not re-worded independently.
    "addon.calico.name": "Calico",
    "addon.calico.desc": "Pod/service network CNI (IPv4, no IPIP, tuned MTU for the data-fabric bond).",
    "addon.kube-ovn.name": "Kube-OVN",
    "addon.kube-ovn.desc": "OVN/OVS-based CNI -- alternative to Calico when you need subnet-per-namespace, static pod IPs, or a distributed gateway/east-west policy model. Pick one CNI, not both.",
    "addon.multus.name": "Multus CNI",
    "addon.multus.desc": "Attach multiple network interfaces to pods (needed alongside SR-IOV/OVS pools).",
    "addon.ovs-cni.name": "OVS CNI",
    "addon.ovs-cni.desc": "Open vSwitch bridge attachment for pods on the data-fabric bond.",
    "addon.whereabouts.name": "Whereabouts",
    "addon.whereabouts.desc": "Cluster-wide IPAM for Multus secondary networks.",
    "addon.sriov-network-device-plugin.name": "SR-IOV Device Plugin",
    "addon.sriov-network-device-plugin.desc": "Exposes SR-IOV VFs on high-throughput pools as schedulable device resources.",
    "addon.bgp-lb.name": "MetalLB (FRR-K8s backend)",
    "addon.bgp-lb.desc": "BGP/BFD-based external LoadBalancer IP announcement for service VIPs, via MetalLB running its FRR-K8s backend (the current recommended default -- MetalLB's older native Go BGP speaker and the plain FRR-sidecar mode are both deprecated). Lets external routers learn a service's VIP as a route instead of relying on ARP/L2, so VIPs can be spread across multiple upstream network segments.",
    "addon.apigateway.name": "Gateway API",
    "addon.apigateway.desc": "Kubernetes Gateway API implementation, exposing north-south HTTP/gRPC routes. Replaces the older Ingress-based setup (ingress-nginx) -- Ingress is now deprecated in favor of Gateway API's HTTPRoute/Gateway resources.",
    "addon.ceph.name": "Ceph (Rook)",
    "addon.ceph.desc": "Hosted block/file storage backed by NVMe OSDs on the storage-role disks.",
    "addon.local-storage-provisioner.name": "Local Storage Provisioner",
    "addon.local-storage-provisioner.desc": "Local-disk StorageClass for pools that don't run Ceph OSDs.",
    "addon.kubevirt.name": "KubeVirt",
    "addon.kubevirt.desc": "Run traditional VMs as Kubernetes-managed workloads (VirtualMachine/VirtualMachineInstance CRDs) alongside containers on the same cluster -- for legacy/VM-only workloads that can't be containerized yet. Also what backs this platform's own KVM-target Cluster API provider (CAPK) when 'kubevirt' is picked as the target cluster's infrastructure_provider.",
    "addon.nvidia-gpu-operator.name": "NVIDIA GPU Operator",
    "addon.nvidia-gpu-operator.desc": "Installs and manages NVIDIA drivers, the container toolkit, and the device plugin on nodes with a GPU -- once running, nodes with real GPU hardware automatically advertise a schedulable nvidia.com/gpu resource, and pods request it the normal Kubernetes way (resources.limits). Only makes sense to enable on a cluster that actually has GPU-bearing hardware assigned to at least one pool (see the 'GPU' filter on the hardware assets page).",
    "addon.cr-registry.name": "Container Registry",
    "addon.cr-registry.desc": "In-cluster OCI registry backed by the CephFS storage class.",
    "addon.dex.name": "Dex (OIDC)",
    "addon.dex.desc": "OIDC identity broker; wires kubectl/console auth to an LDAP backend.",
    "addon.license-manager.name": "Licensing",
    "addon.license-manager.desc": "Central license-server integration for cluster entitlement/capacity validation.",
    "addon.metrics-server.name": "Metrics Server",
    "addon.metrics-server.desc": "Resource metrics API backing kubectl top and HPA.",
    "addon.pm.name": "Prometheus Monitoring",
    "addon.pm.desc": "VictoriaMetrics-based metrics stack + Alertmanager, exposed via the Gateway API.",
    "addon.snmp-alert-forwarder.name": "SNMP Alert Forwarder",
    "addon.snmp-alert-forwarder.desc": "Forwards Alertmanager webhooks as SNMP traps to an external NMS.",
    "addon.fluent-bit.name": "Fluent Bit",
    "addon.fluent-bit.desc": "Node-level log collector, forwards to Fluentd.",
    "addon.fluentd.name": "Fluentd",
    "addon.fluentd.desc": "Aggregates and ships cluster logs to an external syslog/TLS receiver.",
  },
} as const;

export type TranslationKey = keyof typeof translations.zh;

// Compile-time check: every zh key must also exist in en, and vice
// versa -- if this line ever shows a type error, a translation was
// added to one language and forgotten in the other.
type _AssertParity = typeof translations.en extends Record<TranslationKey, string> ? true : never;
type _AssertParityReverse = typeof translations.zh extends Record<keyof typeof translations.en, string>
  ? true
  : never;
const _parityCheck: _AssertParity = true;
const _parityCheckReverse: _AssertParityReverse = true;
void _parityCheck;
void _parityCheckReverse;
