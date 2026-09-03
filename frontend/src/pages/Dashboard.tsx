import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Boxes, Rocket, ServerCog } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { StatusTag } from "../components/ui/StatusTag";
import { useLanguage } from "../lib/i18n";
import type { Cluster, Deployment, HardwareAsset } from "../lib/types";

function StatCard({
  icon: Icon,
  label,
  value,
  sub,
  to,
}: {
  icon: React.ElementType;
  label: string;
  value: number | string;
  sub?: string;
  to: string;
}) {
  return (
    <Link to={to} className="card flex items-center gap-4 p-5 transition hover:border-[var(--color-brand-500)]">
      <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-[var(--color-brand-50)] text-[var(--color-brand-600)]">
        <Icon size={20} />
      </div>
      <div>
        <div className="text-2xl font-bold text-[var(--color-ink)]">{value}</div>
        <div className="text-xs text-[var(--color-ink-muted)]">{label}</div>
        {sub && <div className="mt-0.5 text-[11px] text-[var(--color-ink-faint)]">{sub}</div>}
      </div>
    </Link>
  );
}

export default function Dashboard() {
  const { t } = useLanguage();
  const clustersQ = useQuery({ queryKey: ["clusters"], queryFn: api.clusters.list });
  const assetsQ = useQuery({ queryKey: ["hardware-assets"], queryFn: () => api.hardwareAssets.list() });
  const deploymentsQ = useQuery({ queryKey: ["deployments"], queryFn: () => api.deployments.list() });

  const clusters = clustersQ.data ?? [];
  const assets = assetsQ.data ?? [];
  const deployments = deploymentsQ.data ?? [];

  const readyClusters = clusters.filter((c) => c.status === "ready").length;
  const availableAssets = assets.filter((a) => a.status === "available").length;
  const activeDeployments = deployments.filter(
    (d) => d.phase !== "complete" && d.phase !== "failed",
  ).length;
  const failedDeployments = deployments.filter((d) => d.phase === "failed").length;

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          icon={Boxes}
          label={t("dashboard.totalClusters")}
          value={clusters.length}
          sub={t("dashboard.clustersReady", { count: readyClusters })}
          to="/clusters"
        />
        <StatCard
          icon={ServerCog}
          label={t("dashboard.hardwareAssets")}
          value={assets.length}
          sub={t("dashboard.assetsAvailable", { count: availableAssets })}
          to="/hardware-assets"
        />
        <StatCard
          icon={Rocket}
          label={t("dashboard.activeDeployments")}
          value={activeDeployments}
          sub={t("dashboard.totalDeploymentRecords", { count: deployments.length })}
          to="/deployments"
        />
        <StatCard
          icon={AlertTriangle}
          label={t("dashboard.failedDeployments")}
          value={failedDeployments}
          sub={t("dashboard.clickToInvestigate")}
          to="/deployments"
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="card p-5">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold">{t("dashboard.recentClusters")}</h2>
            <Link to="/clusters" className="text-xs font-medium text-[var(--color-brand-600)]">
              {t("dashboard.viewAll")}
            </Link>
          </div>
          {clusters.length === 0 ? (
            <p className="py-8 text-center text-xs text-[var(--color-ink-faint)]">{t("dashboard.noClustersYet")}</p>
          ) : (
            <ul className="flex flex-col divide-y divide-[var(--color-border)]">
              {clusters.slice(0, 6).map((c: Cluster) => (
                <li key={c.id} className="flex items-center justify-between py-2.5">
                  <Link to={`/clusters/${c.id}`} className="text-sm font-medium hover:text-[var(--color-brand-600)]">
                    {c.name}
                  </Link>
                  <div className="flex items-center gap-3">
                    <span className="text-xs text-[var(--color-ink-faint)]">
                      {t("dashboard.controlPlaneCount", { count: c.control_plane_count })}
                    </span>
                    <StatusTag status={c.status} />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="card p-5">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold">{t("dashboard.recentDeployments")}</h2>
            <Link to="/deployments" className="text-xs font-medium text-[var(--color-brand-600)]">
              {t("dashboard.viewAll")}
            </Link>
          </div>
          {deployments.length === 0 ? (
            <p className="py-8 text-center text-xs text-[var(--color-ink-faint)]">{t("dashboard.noDeploymentsYet")}</p>
          ) : (
            <ul className="flex flex-col divide-y divide-[var(--color-border)]">
              {deployments.slice(0, 6).map((d: Deployment) => (
                <li key={d.id} className="flex items-center justify-between py-2.5">
                  <Link
                    to={`/deployments/${d.id}`}
                    className="mono text-xs font-medium hover:text-[var(--color-brand-600)]"
                  >
                    {d.id.slice(0, 8)}
                  </Link>
                  <StatusTag status={d.phase} />
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <AssetInventorySummary assets={assets} />
    </div>
  );
}

function AssetInventorySummary({ assets }: { assets: HardwareAsset[] }) {
  const { t } = useLanguage();
  const byStatus = assets.reduce<Record<string, number>>((acc, a) => {
    acc[a.status] = (acc[a.status] ?? 0) + 1;
    return acc;
  }, {});
  const totalCores = assets.reduce((sum, a) => sum + a.cpu_sockets * a.cpu_cores_per_socket, 0);
  const totalMemory = assets.reduce((sum, a) => sum + a.memory_gb, 0);

  return (
    <div className="card p-5">
      <h2 className="mb-4 text-sm font-semibold">{t("dashboard.assetInventoryOverview")}</h2>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Metric label={t("dashboard.totalPhysicalCores")} value={totalCores} />
        <Metric label={t("dashboard.totalMemory")} value={`${totalMemory.toLocaleString()} GB`} />
        {Object.entries(byStatus).map(([status, count]) => (
          <div key={status} className="flex flex-col gap-1">
            <StatusTag status={status} />
            <span className="text-lg font-bold">{count}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs text-[var(--color-ink-muted)]">{label}</span>
      <span className="text-lg font-bold">{value}</span>
    </div>
  );
}
