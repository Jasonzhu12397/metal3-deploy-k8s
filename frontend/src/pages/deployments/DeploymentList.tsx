import { useQuery } from "@tanstack/react-query";
import { Rocket } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";
import { EmptyState } from "../../components/ui/EmptyState";
import { StatusTag } from "../../components/ui/StatusTag";
import { useLanguage } from "../../lib/i18n";

export default function DeploymentList() {
  const { t } = useLanguage();
  const { data: deployments, isLoading } = useQuery({
    queryKey: ["deployments"],
    queryFn: () => api.deployments.list(),
  });
  const { data: clusters } = useQuery({ queryKey: ["clusters"], queryFn: api.clusters.list });
  const clusterName = new Map((clusters ?? []).map((c) => [c.id, c.name]));

  return (
    <div className="card overflow-hidden">
      {isLoading ? (
        <p className="p-8 text-center text-xs text-[var(--color-ink-faint)]">{t("dep.loading")}</p>
      ) : !deployments || deployments.length === 0 ? (
        <EmptyState icon={Rocket} title={t("dep.emptyTitle")} hint={t("dep.emptyHint")} />
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[var(--color-border)] text-left text-xs text-[var(--color-ink-muted)]">
              <th className="px-4 py-2.5 font-medium">{t("dep.colId")}</th>
              <th className="px-4 py-2.5 font-medium">{t("dep.colCluster")}</th>
              <th className="px-4 py-2.5 font-medium">{t("dep.colPhase")}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--color-border)]">
            {deployments.map((d) => (
              <tr key={d.id} className="hover:bg-[var(--color-bg)]">
                <td className="px-4 py-3">
                  <Link to={`/deployments/${d.id}`} className="mono font-medium text-[var(--color-brand-600)]">
                    {d.id}
                  </Link>
                </td>
                <td className="px-4 py-3">
                  <Link to={`/clusters/${d.cluster_id}`} className="text-[var(--color-ink-muted)] hover:text-[var(--color-brand-600)]">
                    {clusterName.get(d.cluster_id) ?? d.cluster_id.slice(0, 8)}
                  </Link>
                </td>
                <td className="px-4 py-3">
                  <StatusTag status={d.phase} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
