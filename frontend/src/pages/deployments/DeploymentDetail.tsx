import { useQuery } from "@tanstack/react-query";
import { Check, CircleDashed, Loader2, XCircle } from "lucide-react";
import { useParams } from "react-router-dom";
import { api } from "../../lib/api";
import { StatusTag } from "../../components/ui/StatusTag";
import { useDeploymentSocket } from "../../lib/useDeploymentSocket";
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

const PHASE_LABEL: Record<DeploymentPhase, string> = {
  queued: "已排队",
  generating_manifests: "渲染清单",
  bootstrapping_ephemeral_node: "确认管理集群可达",
  applying_bmh: "确认 BareMetalHost",
  waiting_for_hosts: "等待主机就绪",
  applying_cluster: "apply 集群资源",
  waiting_for_control_plane: "等待控制面就绪",
  installing_addons: "安装组件",
  complete: "完成",
  failed: "失败",
};

export default function DeploymentDetail() {
  const { id = "" } = useParams();
  const { data: deployment } = useQuery({
    queryKey: ["deployment", id],
    queryFn: () => api.deployments.get(id),
    refetchInterval: 5000,
  });
  const { events, connected } = useDeploymentSocket(id);

  if (!deployment) return <p className="text-xs text-[var(--color-ink-faint)]">加载中...</p>;

  const currentPhase = deployment.phase;
  const currentIndex = PHASE_ORDER.indexOf(currentPhase);
  const failed = currentPhase === "failed";

  return (
    <div className="flex flex-col gap-5">
      <div className="card flex items-center justify-between p-5">
        <div>
          <h2 className="mono text-base font-bold">{deployment.id}</h2>
          <p className="mt-1 text-xs text-[var(--color-ink-faint)]">
            实时进度 {connected ? "已连接" : "未连接（展示最近一次已知状态）"}
          </p>
        </div>
        <StatusTag status={deployment.phase} />
      </div>

      <div className="card p-5">
        <h3 className="mb-4 text-sm font-semibold">部署阶段</h3>
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
                  {PHASE_LABEL[phase]}
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
        <h3 className="mb-3 text-sm font-semibold">事件日志</h3>
        {events.length === 0 ? (
          <p className="text-xs text-[var(--color-ink-faint)]">
            还没有收到 WebSocket 事件（如果部署已经完成，历史事件不会重放，看上面的阶段状态即可）
          </p>
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
