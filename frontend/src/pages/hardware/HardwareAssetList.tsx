import { useQuery } from "@tanstack/react-query";
import { Cpu, LayoutGrid, Rows3, ServerCog } from "lucide-react";
import { useState } from "react";
import { api } from "../../lib/api";
import { useLanguage } from "../../lib/i18n";
import { CoreMap } from "../../components/ui/CoreMap";
import { EmptyState } from "../../components/ui/EmptyState";
import { StatusTag } from "../../components/ui/StatusTag";
import { HardwareAssetDrawer } from "./HardwareAssetDrawer";
import type { AssetStatus } from "../../lib/types";

type TranslationKey = Parameters<ReturnType<typeof useLanguage>["t"]>[0];

const STATUS_FILTER_KEYS: { value: AssetStatus | "all"; key: TranslationKey }[] = [
  { value: "all", key: "hw.status.all" },
  { value: "available", key: "hw.status.available" },
  { value: "reserved", key: "hw.status.reserved" },
  { value: "provisioned", key: "hw.status.provisioned" },
  { value: "discovered", key: "hw.status.discovered" },
];

export default function HardwareAssetList() {
  const { t } = useLanguage();
  const [view, setView] = useState<"rack" | "table">("rack");
  const [statusFilter, setStatusFilter] = useState<AssetStatus | "all">("all");
  const [gpuOnly, setGpuOnly] = useState(false);
  const [openAssetId, setOpenAssetId] = useState<string | null>(null);

  const { data: assets, isLoading } = useQuery({
    queryKey: ["hardware-assets", statusFilter, gpuOnly],
    queryFn: () =>
      api.hardwareAssets.list({
        status: statusFilter === "all" ? undefined : statusFilter,
        has_gpu: gpuOnly ? true : undefined,
      }),
  });

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-[var(--color-ink-muted)]">{t("hw.hint")}</p>
        <div className="flex items-center gap-2">
          <div className="flex gap-1 rounded-lg border border-[var(--color-border-strong)] p-0.5">
            {STATUS_FILTER_KEYS.map((f) => (
              <button
                key={f.value}
                onClick={() => setStatusFilter(f.value)}
                className={`rounded-md px-2.5 py-1 text-[11px] font-medium transition ${
                  statusFilter === f.value
                    ? "bg-[var(--color-brand-500)] text-white"
                    : "text-[var(--color-ink-muted)] hover:text-[var(--color-ink)]"
                }`}
              >
                {t(f.key)}
              </button>
            ))}
          </div>
          <button
            onClick={() => setGpuOnly((v) => !v)}
            className={`flex items-center gap-1 rounded-lg border px-2.5 py-1 text-[11px] font-medium transition ${
              gpuOnly
                ? "border-[var(--color-brand-500)] bg-[var(--color-brand-500)] text-white"
                : "border-[var(--color-border-strong)] text-[var(--color-ink-muted)] hover:text-[var(--color-ink)]"
            }`}
            title={t("hw.gpuOnlyTitle")}
          >
            <Cpu size={12} /> {t("hw.gpuOnly")}
          </button>
          <div className="flex gap-1 rounded-lg border border-[var(--color-border-strong)] p-0.5">
            <button
              onClick={() => setView("rack")}
              className={`flex items-center gap-1 rounded-md px-2.5 py-1 text-[11px] font-medium transition ${
                view === "rack" ? "bg-[var(--color-brand-500)] text-white" : "text-[var(--color-ink-muted)]"
              }`}
            >
              <LayoutGrid size={12} /> {t("hw.viewRack")}
            </button>
            <button
              onClick={() => setView("table")}
              className={`flex items-center gap-1 rounded-md px-2.5 py-1 text-[11px] font-medium transition ${
                view === "table" ? "bg-[var(--color-brand-500)] text-white" : "text-[var(--color-ink-muted)]"
              }`}
            >
              <Rows3 size={12} /> {t("hw.viewTable")}
            </button>
          </div>
        </div>
      </div>

      {isLoading ? (
        <p className="text-xs text-[var(--color-ink-faint)]">{t("hw.loading")}</p>
      ) : !assets || assets.length === 0 ? (
        <div className="card">
          <EmptyState icon={ServerCog} title={t("hw.emptyTitle")} hint={t("hw.emptyHint")} />
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
                    {a.vendor ?? t("hw.unknownVendor")} {a.model ?? ""}
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
                <p className="text-[11px] text-[var(--color-ink-faint)]">{t("hw.topologyNotSynced")}</p>
              )}

              <div className="flex items-center justify-between text-[11px] text-[var(--color-ink-muted)]">
                <span>{t("hw.coresAndMemory", { sockets: a.cpu_sockets, cores: a.cpu_cores_per_socket, memory: a.memory_gb })}</span>
                <span>{t("hw.nicsAndDisks", { nics: a.nics.length, disks: a.disks.length })}</span>
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                {a.has_gpu && (
                  <span className="flex items-center gap-1 w-fit rounded-full bg-[var(--color-success-soft)] px-2 py-0.5 text-[11px] font-medium text-[var(--color-success)]">
                    <Cpu size={10} /> {a.gpu_count}× {a.gpu_model ?? "GPU"}
                  </span>
                )}
                {a.node_pool_name && (
                  <span className="w-fit rounded-full bg-[var(--color-brand-50)] px-2 py-0.5 text-[11px] font-medium text-[var(--color-brand-600)]">
                    {a.node_pool_name}
                  </span>
                )}
              </div>
            </button>
          ))}
        </div>
      ) : (
        <div className="card overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--color-border)] text-left text-xs text-[var(--color-ink-muted)]">
                <th className="px-4 py-2.5 font-medium">{t("hw.colName")}</th>
                <th className="px-4 py-2.5 font-medium">{t("hw.colStatus")}</th>
                <th className="px-4 py-2.5 font-medium">{t("hw.colCpu")}</th>
                <th className="px-4 py-2.5 font-medium">{t("hw.colMemory")}</th>
                <th className="px-4 py-2.5 font-medium">{t("hw.colGpu")}</th>
                <th className="px-4 py-2.5 font-medium">{t("hw.colNicsDisks")}</th>
                <th className="px-4 py-2.5 font-medium">{t("hw.colPool")}</th>
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
                    {a.has_gpu ? `${a.gpu_count}× ${a.gpu_model ?? "GPU"}` : "—"}
                  </td>
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
