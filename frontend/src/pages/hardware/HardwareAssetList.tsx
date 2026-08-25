import { useQuery } from "@tanstack/react-query";
import { LayoutGrid, Rows3, ServerCog } from "lucide-react";
import { useState } from "react";
import { api } from "../../lib/api";
import { CoreMap } from "../../components/ui/CoreMap";
import { EmptyState } from "../../components/ui/EmptyState";
import { StatusTag } from "../../components/ui/StatusTag";
import { HardwareAssetDrawer } from "./HardwareAssetDrawer";
import type { AssetStatus } from "../../lib/types";

const STATUS_FILTERS: { value: AssetStatus | "all"; label: string }[] = [
  { value: "all", label: "全部" },
  { value: "available", label: "空闲" },
  { value: "reserved", label: "已分配" },
  { value: "provisioned", label: "运行中" },
  { value: "discovered", label: "待校验" },
];

export default function HardwareAssetList() {
  const [view, setView] = useState<"rack" | "table">("rack");
  const [statusFilter, setStatusFilter] = useState<AssetStatus | "all">("all");
  const [openAssetId, setOpenAssetId] = useState<string | null>(null);

  const { data: assets, isLoading } = useQuery({
    queryKey: ["hardware-assets", statusFilter],
    queryFn: () => api.hardwareAssets.list(statusFilter === "all" ? undefined : { status: statusFilter }),
  });

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-[var(--color-ink-muted)]">
          物理机注册后，Ironic 会自动探测 CPU/内存/网卡/磁盘 —— 点开一台机器同步结果、修正网卡/磁盘角色。
        </p>
        <div className="flex items-center gap-2">
          <div className="flex gap-1 rounded-lg border border-[var(--color-border-strong)] p-0.5">
            {STATUS_FILTERS.map((f) => (
              <button
                key={f.value}
                onClick={() => setStatusFilter(f.value)}
                className={`rounded-md px-2.5 py-1 text-[11px] font-medium transition ${
                  statusFilter === f.value
                    ? "bg-[var(--color-brand-500)] text-white"
                    : "text-[var(--color-ink-muted)] hover:text-[var(--color-ink)]"
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>
          <div className="flex gap-1 rounded-lg border border-[var(--color-border-strong)] p-0.5">
            <button
              onClick={() => setView("rack")}
              className={`flex items-center gap-1 rounded-md px-2.5 py-1 text-[11px] font-medium transition ${
                view === "rack" ? "bg-[var(--color-brand-500)] text-white" : "text-[var(--color-ink-muted)]"
              }`}
            >
              <LayoutGrid size={12} /> 机架视图
            </button>
            <button
              onClick={() => setView("table")}
              className={`flex items-center gap-1 rounded-md px-2.5 py-1 text-[11px] font-medium transition ${
                view === "table" ? "bg-[var(--color-brand-500)] text-white" : "text-[var(--color-ink-muted)]"
              }`}
            >
              <Rows3 size={12} /> 列表
            </button>
          </div>
        </div>
      </div>

      {isLoading ? (
        <p className="text-xs text-[var(--color-ink-faint)]">加载中...</p>
      ) : !assets || assets.length === 0 ? (
        <div className="card">
          <EmptyState
            icon={ServerCog}
            title="还没有硬件资产"
            hint='去"裸金属主机"注册一台物理机，Ironic 完成探测后会自动出现在这里。'
          />
        </div>
      ) : view === "rack" ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {assets.map((a) => (
            <button
              key={a.id}
              onClick={() => setOpenAssetId(a.id)}
              className="card flex flex-col gap-3 p-4 text-left transition hover:border-[var(--color-brand-500)]"
            >
              <div className="flex items-start justify-between">
                <div className="min-w-0">
                  <div className="truncate text-sm font-bold">{a.name}</div>
                  <div className="truncate text-[11px] text-[var(--color-ink-faint)]">
                    {a.vendor ?? "未知厂商"} {a.model ?? ""}
                  </div>
                </div>
                <StatusTag status={a.status} />
              </div>

              {a.cpu_sockets > 0 ? (
                <CoreMap
                  compact
                  sockets={a.cpu_sockets}
                  coresPerSocket={a.cpu_cores_per_socket}
                  threadsPerCore={a.cpu_threads_per_core}
                  reservedPerSocket={0}
                />
              ) : (
                <p className="text-[11px] text-[var(--color-ink-faint)]">尚未同步 CPU 拓扑</p>
              )}

              <div className="flex items-center justify-between text-[11px] text-[var(--color-ink-muted)]">
                <span>
                  {a.cpu_sockets}×{a.cpu_cores_per_socket} 核 · {a.memory_gb}GB
                </span>
                <span>{a.nics.length} 网卡 · {a.disks.length} 磁盘</span>
              </div>
              {a.node_pool_name && (
                <span className="w-fit rounded-full bg-[var(--color-brand-50)] px-2 py-0.5 text-[11px] font-medium text-[var(--color-brand-600)]">
                  {a.node_pool_name}
                </span>
              )}
            </button>
          ))}
        </div>
      ) : (
        <div className="card overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--color-border)] text-left text-xs text-[var(--color-ink-muted)]">
                <th className="px-4 py-2.5 font-medium">名称</th>
                <th className="px-4 py-2.5 font-medium">状态</th>
                <th className="px-4 py-2.5 font-medium">CPU</th>
                <th className="px-4 py-2.5 font-medium">内存</th>
                <th className="px-4 py-2.5 font-medium">网卡/磁盘</th>
                <th className="px-4 py-2.5 font-medium">所属池</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--color-border)]">
              {assets.map((a) => (
                <tr
                  key={a.id}
                  className="cursor-pointer hover:bg-[var(--color-bg)]"
                  onClick={() => setOpenAssetId(a.id)}
                >
                  <td className="px-4 py-3 font-medium text-[var(--color-brand-600)]">{a.name}</td>
                  <td className="px-4 py-3">
                    <StatusTag status={a.status} />
                  </td>
                  <td className="px-4 py-3 text-[var(--color-ink-muted)]">
                    {a.cpu_sockets}×{a.cpu_cores_per_socket}×{a.cpu_threads_per_core}t
                  </td>
                  <td className="px-4 py-3 text-[var(--color-ink-muted)]">{a.memory_gb} GB</td>
                  <td className="px-4 py-3 text-[var(--color-ink-muted)]">
                    {a.nics.length} / {a.disks.length}
                  </td>
                  <td className="px-4 py-3 text-[var(--color-ink-muted)]">{a.node_pool_name ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {openAssetId && <HardwareAssetDrawer assetId={openAssetId} onClose={() => setOpenAssetId(null)} />}
    </div>
  );
}
