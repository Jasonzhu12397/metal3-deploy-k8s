import { useQuery } from "@tanstack/react-query";
import { Check, CircleDashed, Loader2, XCircle } from "lucide-react";
import { useParams } from "react-router-dom";
import { api } from "../../lib/api";
import { StatusTag } from "../../components/ui/StatusTag";
import { useDeploymentSocket } from "../../lib/useDeploymentSocket";
import { useLanguage } from "../../lib/i18n";
import type { DeploymentPhase } from "../../lib/types";

const PHASE_ORDER: DeploymentPhase[] = [
  "queued",
  "generating_manifests",
  "bootstrapping_ephemeral_node",
  "applying_bmh",
  "waiting_for_hosts",
  "applying_cluster",
  "waiting_for_control_plane",
  "installing_addons",
  "complete",
];
// Deliberately NOT in PHASE_ORDER above: "pivoting_to_target_cluster" is
// opt-in (cluster_spec["pivot_to_self_hosting"]) and most deployments
// never go through it -- always rendering it in the fixed stepper would
// show every non-pivoting deployment a step that will never actually
// run, permanently stuck looking "pending". It still needs an entry in
// PHASE_LABEL_KEYS below (TypeScript's Record<DeploymentPhase, ...>
// requires every enum value), so the phase renders correctly wherever
// it DOES appear (the event log, a failed-here state) for the
// deployments that do use it.

const PHASE_LABEL_KEYS: Record<DeploymentPhase, `dep.phase.${DeploymentPhase}`> = {
  queued: "dep.phase.queued",
  generating_manifests: "dep.phase.generating_manifests",
  bootstrapping_ephemeral_node: "dep.phase.bootstrapping_ephemeral_node",
  applying_bmh: "dep.phase.applying_bmh",
  waiting_for_hosts: "dep.phase.waiting_for_hosts",
  applying_cluster: "dep.phase.applying_cluster",
  waiting_for_control_plane: "dep.phase.waiting_for_control_plane",
  installing_addons: "dep.phase.installing_addons",
  pivoting_to_target_cluster: "dep.phase.pivoting_to_target_cluster",
  complete: "dep.phase.complete",
  failed: "dep.phase.failed",
};

export default function DeploymentDetail() {
  const { t } = useLanguage();
  const { id = "" } = useParams();
  const { data: deployment } = useQuery({
    queryKey: ["deployment", id],
    queryFn: () => api.deployments.get(id),
    refetchInterval: 5000,
  });
  const { events, connected } = useDeploymentSocket(id);

  if (!deployment) return <p className="text-xs text-[var(--color-ink-faint)]">{t("dep.loadingDetail")}</p>;

  const currentPhase = deployment.phase;
  const currentIndex = PHASE_ORDER.indexOf(currentPhase);
  const failed = currentPhase === "failed";

  return (
    <div className="flex flex-col gap-5">
      <div className="card flex items-center justify-between p-5">
        <div>
          <h2 className="mono text-base font-bold">{deployment.id}</h2>
          <p className="mt-1 text-xs text-[var(--color-ink-faint)]">
            {t("dep.liveProgress")} {connected ? t("dep.connected") : t("dep.disconnected")}
          </p>
        </div>
        <StatusTag status={deployment.phase} />
      </div>

      <div className="card p-5">
        <h3 className="mb-4 text-sm font-semibold">{t("dep.stages")}</h3>
        <ol className="flex flex-col gap-0.5">
          {PHASE_ORDER.map((phase, i) => {
            const done = !failed && currentIndex > i;
            const active = !failed && currentIndex === i;
            const isFailedHere = failed && i === currentIndex;
            return (
              <li key={phase} className="flex items-start gap-3 py-1.5">
                <div className="mt-0.5">
                  {done ? (
                    <Check size={16} className="text-[var(--color-success)]" />
                  ) : active ? (
                    <Loader2 size={16} className="animate-spin text-[var(--color-processing)]" />
                  ) : isFailedHere ? (
                    <XCircle size={16} className="text-[var(--color-danger)]" />
                  ) : (
                    <CircleDashed size={16} className="text-[var(--color-ink-faint)]" />
                  )}
                </div>
                <span
                  className={`text-sm ${
                    done || active
                      ? "font-medium text-[var(--color-ink)]"
                      : "text-[var(--color-ink-faint)]"
                  }`}
                >
                  {t(PHASE_LABEL_KEYS[phase])}
                </span>
              </li>
            );
          })}
        </ol>

        {deployment.error_message && (
          <div className="mt-4 rounded-lg border border-[var(--color-danger)]/30 bg-[var(--color-danger-soft)] p-3 text-xs text-[var(--color-danger)]">
            {deployment.error_message}
          </div>
        )}
      </div>

      <div className="card p-5">
        <h3 className="mb-3 text-sm font-semibold">{t("dep.eventLog")}</h3>
        {events.length === 0 ? (
          <p className="text-xs text-[var(--color-ink-faint)]">{t("dep.noEvents")}</p>
        ) : (
          <ul className="mono flex flex-col gap-1.5 text-xs">
            {events.map((e, i) => (
              <li key={i} className="flex gap-2">
                <span className="shrink-0 text-[var(--color-brand-600)]">[{e.phase}]</span>
                <span className="text-[var(--color-ink-muted)]">{e.message}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
