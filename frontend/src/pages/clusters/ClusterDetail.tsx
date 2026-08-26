import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileCode2, Layers, Plus, Rocket, Settings2, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../../lib/api";
import { CodeBlock } from "../../components/ui/CodeBlock";
import { CoreMap } from "../../components/ui/CoreMap";
import { EmptyState } from "../../components/ui/EmptyState";
import { StatusTag } from "../../components/ui/StatusTag";
import { AssignAssetsModal } from "./AssignAssetsModal";
import type { HardwareAsset } from "../../lib/types";

const TABS = [
  { key: "pools", label: "节点池", icon: Layers },
  { key: "manifests", label: "生成的清单", icon: FileCode2 },
  { key: "deployments", label: "部署", icon: Rocket },
] as const;

export default function ClusterDetail() {
  const { id = "" } = useParams();
  const [tab, setTab] = useState<(typeof TABS)[number]["key"]>("pools");

  const { data: cluster } = useQuery({ queryKey: ["cluster", id], queryFn: () => api.clusters.get(id) });

  if (!cluster) return <p className="text-xs text-[var(--color-ink-faint)]">加载中...</p>;

  const isCloud = cluster.infrastructure_provider !== "metal3";

  return (
    <div className="flex flex-col gap-5">
      <div className="card flex items-center justify-between p-5">
        <div>
          <div className="flex items-center gap-2.5">
            <h2 className="text-lg font-bold">{cluster.name}</h2>
            <StatusTag status={cluster.status} />
            <span className="rounded-full bg-[var(--color-idle-soft)] px-2 py-0.5 text-[11px] font-medium text-[var(--color-ink-muted)]">
              {cluster.infrastructure_provider}
            </span>
          </div>
          <p className="mono mt-1 text-xs text-[var(--color-ink-muted)]">
            {cluster.namespace} · {cluster.control_plane_count} 控制面 ·{" "}
            {cluster.control_plane_endpoint ?? "未设置 endpoint"}
          </p>
        </div>
      </div>

      <div className="flex gap-1 border-b border-[var(--color-border)]">
        {TABS.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`flex items-center gap-1.5 border-b-2 px-3.5 py-2.5 text-[13px] font-medium transition ${
              tab === key
                ? "border-[var(--color-brand-500)] text-[var(--color-brand-600)]"
                : "border-transparent text-[var(--color-ink-muted)] hover:text-[var(--color-ink)]"
            }`}
          >
            <Icon size={14} /> {label}
          </button>
        ))}
      </div>

      {tab === "pools" && (isCloud ? <CloudPoolsNotice provider={cluster.infrastructure_provider} /> : <PoolsTab clusterId={id} />)}
      {tab === "manifests" && <ManifestsTab clusterId={id} />}
      {tab === "deployments" && <DeploymentsTab clusterId={id} />}
    </div>
  );
}

function CloudPoolsNotice({ provider }: { provider: string }) {
  return (
    <div className="card p-8 text-center">
      <p className="text-sm font-medium">{provider} 集群没有"节点池"硬件分配这一步</p>
      <p className="mx-auto mt-2 max-w-md text-xs text-[var(--color-ink-muted)]">
        {provider === "openstack" && "OpenStack 集群的 worker 池（名称/数量/flavor/image）是建集群时直接声明的，不需要（也没有）物理硬件可选。"}
        {provider === "vsphere" && "vSphere 集群的 worker 池（名称/数量/flavor/VM 模板）是建集群时直接声明的，不需要（也没有）物理硬件可选。"}
        {provider === "kubevirt" && "KubeVirt 集群的 worker 池（名称/数量/flavor/DataVolume）是建集群时直接声明的，VM 跑在装了 KubeVirt 的管理集群里，不需要单独的物理硬件。"}
        {" "}要改 worker 池配置，目前需要重建集群；直接去"生成的清单"标签页看渲染结果，或者去"部署"标签页发起部署。
      </p>
    </div>
  );
}

function PoolsTab({ clusterId }: { clusterId: string }) {
  const qc = useQueryClient();
  const [showAssign, setShowAssign] = useState(false);
  const { data: pools, isLoading } = useQuery({
    queryKey: ["cluster-pools", clusterId],
    queryFn: () => api.clusters.pools(clusterId),
  });
  const { data: allAssets } = useQuery({
    queryKey: ["hardware-assets"],
    queryFn: () => api.hardwareAssets.list(),
  });

  const unassignMutation = useMutation({
    mutationFn: ({ pool, assetId }: { pool: string; assetId: string }) =>
      api.clusters.unassignAsset(clusterId, pool, assetId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cluster-pools", clusterId] });
      qc.invalidateQueries({ queryKey: ["hardware-assets"] });
    },
  });

  const assetById = new Map((allAssets ?? []).map((a) => [a.id, a]));
  const poolEntries = Object.entries(pools ?? {});

  return (
    <div className="flex flex-col gap-4">
      <div className="flex justify-end">
        <button className="btn btn-primary" onClick={() => setShowAssign(true)}>
          <Plus size={14} /> 分配硬件到节点池
        </button>
      </div>

      {isLoading ? (
        <p className="text-xs text-[var(--color-ink-faint)]">加载中...</p>
      ) : poolEntries.length === 0 ? (
        <div className="card">
          <EmptyState
            icon={Layers}
            title="这个集群还没有节点池"
            hint="从空闲的硬件资产库存里挑机器，指定角色（控制面/worker）和 CPU 预留策略，组成一个节点池。"
            action={
              <button className="btn btn-primary mt-2" onClick={() => setShowAssign(true)}>
                <Plus size={14} /> 分配硬件到节点池
              </button>
            }
          />
        </div>
      ) : (
        poolEntries.map(([poolName, assignments]) => {
          const isControlPlane = assignments[0]?.role === "control-plane";
          return (
          <div key={poolName} className="card p-5">
            <div className="mb-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold">{poolName}</h3>
                <span className="rounded-full bg-[var(--color-idle-soft)] px-2 py-0.5 text-[11px] font-medium text-[var(--color-ink-muted)]">
                  {assignments[0]?.role ?? "worker"}
                </span>
                <span className="text-xs text-[var(--color-ink-faint)]">{assignments.length} 台</span>
                {isControlPlane && (
                  <span className="text-[11px] text-[var(--color-ink-faint)]">
                    · 驱动 KubeadmControlPlane 副本数，不会生成 MachineDeployment
                    {assignments.length === 1 && "（单机 = single-node 集群，会自动去掉控制面 taint）"}
                  </span>
                )}
              </div>
            </div>
            <ul className="flex flex-col gap-3">
              {assignments.map((a) => {
                const asset = assetById.get(a.asset_id) as HardwareAsset | undefined;
                return (
                  <li
                    key={a.id}
                    className="flex flex-col gap-2 rounded-lg border border-[var(--color-border)] p-3 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div>
                      <div className="text-sm font-medium">{asset?.name ?? a.asset_id.slice(0, 8)}</div>
                      <div className="mono mt-0.5 text-[11px] text-[var(--color-ink-faint)]">
                        reserved_cpus: {a.computed_reserved_cpus || "—"}
                      </div>
                      <div className="mt-0.5 text-[11px] text-[var(--color-ink-faint)]">
                        隔离可用 {a.computed_isolated_cpu_count} 核 · {a.hugepage_type} ×{" "}
                        {a.hugepage_count_1gb}
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      {asset && (
                        <CoreMap
                          compact
                          sockets={asset.cpu_sockets}
                          coresPerSocket={asset.cpu_cores_per_socket}
                          threadsPerCore={asset.cpu_threads_per_core}
                          reservedPerSocket={a.reserved_cores_per_socket}
                        />
                      )}
                      <button
                        className="btn-ghost btn !p-1.5"
                        title="从节点池移除"
                        onClick={() => unassignMutation.mutate({ pool: poolName, assetId: a.asset_id })}
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
          );
        })
      )}

      {showAssign && <AssignAssetsModal clusterId={clusterId} onClose={() => setShowAssign(false)} />}
    </div>
  );
}

function ManifestsTab({ clusterId }: { clusterId: string }) {
  const [activeYaml, setActiveYaml] = useState<"bmh" | "cluster" | string>("bmh");

  const generateMutation = useMutation({
    mutationFn: () => api.clusters.generateManifests(clusterId),
  });

  const bundle = generateMutation.data;

  return (
    <div className="flex flex-col gap-4">
      <div className="card flex items-center justify-between p-4">
        <p className="text-xs text-[var(--color-ink-muted)]">
          从已分配的硬件资产直接渲染 bmh.yaml / 集群配置 / 每台机器的网络绑定策略 —— 纯预览，不会 apply 到管理集群。
        </p>
        <button className="btn btn-primary shrink-0" onClick={() => generateMutation.mutate()}>
          <Settings2 size={14} /> {generateMutation.isPending ? "生成中..." : "生成清单"}
        </button>
      </div>

      {generateMutation.isError && (
        <p className="text-xs text-[var(--color-danger)]">{(generateMutation.error as Error).message}</p>
      )}

      {bundle && (
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap gap-1.5">
            <TabPill active={activeYaml === "bmh"} onClick={() => setActiveYaml("bmh")} label="bmh.yaml" />
            <TabPill
              active={activeYaml === "cluster"}
              onClick={() => setActiveYaml("cluster")}
              label="集群配置 (CAPI)"
            />
            {Object.keys(bundle.network_policies).map((key) => (
              <TabPill key={key} active={activeYaml === key} onClick={() => setActiveYaml(key)} label={key} />
            ))}
          </div>
          <CodeBlock
            code={
              activeYaml === "bmh"
                ? bundle.bmh_yaml
                : activeYaml === "cluster"
                  ? bundle.cluster_config_yaml
                  : (bundle.network_policies[activeYaml] ?? "")
            }
          />
        </div>
      )}
    </div>
  );
}

function TabPill({ active, onClick, label }: { active: boolean; onClick: () => void; label: string }) {
  return (
    <button
      onClick={onClick}
      className={`mono rounded-md px-2.5 py-1 text-[11px] font-medium transition ${
        active
          ? "bg-[var(--color-brand-500)] text-white"
          : "bg-[var(--color-idle-soft)] text-[var(--color-ink-muted)] hover:text-[var(--color-ink)]"
      }`}
    >
      {label}
    </button>
  );
}

function DeploymentsTab({ clusterId }: { clusterId: string }) {
  const qc = useQueryClient();
  const { data: deployments, isLoading } = useQuery({
    queryKey: ["deployments", clusterId],
    queryFn: () => api.deployments.list(clusterId),
  });

  const startMutation = useMutation({
    mutationFn: () => api.deployments.create(clusterId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["deployments", clusterId] }),
  });

  return (
    <div className="flex flex-col gap-4">
      <div className="flex justify-end">
        <button className="btn btn-primary" onClick={() => startMutation.mutate()} disabled={startMutation.isPending}>
          <Rocket size={14} /> {startMutation.isPending ? "提交中..." : "发起部署"}
        </button>
      </div>
      {startMutation.isError && (
        <p className="text-xs text-[var(--color-danger)]">{(startMutation.error as Error).message}</p>
      )}

      <div className="card overflow-hidden">
        {isLoading ? (
          <p className="p-8 text-center text-xs text-[var(--color-ink-faint)]">加载中...</p>
        ) : !deployments || deployments.length === 0 ? (
          <EmptyState icon={Rocket} title="还没有部署过这个集群" hint="点击右上角「发起部署」把当前节点池配置 apply 到管理集群。" />
        ) : (
          <ul className="divide-y divide-[var(--color-border)]">
            {deployments.map((d) => (
              <li key={d.id} className="flex items-center justify-between px-4 py-3">
                <Link to={`/deployments/${d.id}`} className="mono text-sm font-medium hover:text-[var(--color-brand-600)]">
                  {d.id}
                </Link>
                <StatusTag status={d.phase} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
