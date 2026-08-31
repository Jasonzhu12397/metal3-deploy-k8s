import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Plus, RefreshCw, Sparkles, X } from "lucide-react";
import { useState } from "react";
import { api, ApiError } from "../../lib/api";
import { EmptyState } from "../../components/ui/EmptyState";
import { StatusTag } from "../../components/ui/StatusTag";

export default function AIWorkloads() {
  const qc = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);

  const { data: workloads, isLoading } = useQuery({
    queryKey: ["ai-workloads"],
    queryFn: () => api.aiWorkloads.list(),
  });

  const removeMutation = useMutation({
    mutationFn: (id: string) => api.aiWorkloads.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ai-workloads"] }),
  });

  const redeployMutation = useMutation({
    mutationFn: (id: string) => api.aiWorkloads.redeploy(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ai-workloads"] }),
  });

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <p className="text-xs text-[var(--color-ink-muted)]">
          把 vLLM 推理服务一键部署到已经建好的目标集群上（不是集群 addon，是跑在集群里的一个工作负载）。目标集群的控制面必须已经 Ready——kubeconfig 还没生成的话部署会失败，可以之后点「重试部署」。
        </p>
        <button className="btn btn-primary shrink-0" onClick={() => setShowCreate(true)}>
          <Plus size={14} /> 部署 vLLM
        </button>
      </div>

      {isLoading ? (
        <p className="text-xs text-[var(--color-ink-faint)]">加载中...</p>
      ) : !workloads || workloads.length === 0 ? (
        <div className="card">
          <EmptyState icon={Sparkles} title="还没有部署任何 AI 工作负载" hint="点右上角「部署 vLLM」把推理服务部署到目标集群" />
        </div>
      ) : (
        <div className="card overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--color-border)] text-left text-xs text-[var(--color-ink-muted)]">
                <th className="px-4 py-2.5 font-medium">名称</th>
                <th className="px-4 py-2.5 font-medium">模型</th>
                <th className="px-4 py-2.5 font-medium">GPU × 副本</th>
                <th className="px-4 py-2.5 font-medium">状态</th>
                <th className="px-4 py-2.5 font-medium">Endpoint</th>
                <th className="px-4 py-2.5 font-medium"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--color-border)]">
              {workloads.map((w) => (
                <tr key={w.id}>
                  <td className="px-4 py-3 font-medium">{w.name}</td>
                  <td className="mono px-4 py-3 text-[var(--color-ink-muted)]">{w.model_id}</td>
                  <td className="px-4 py-3 text-[var(--color-ink-muted)]">
                    {w.gpu_count} × {w.replicas}
                  </td>
                  <td className="px-4 py-3">
                    <StatusTag status={w.status} />
                    {w.status === "failed" && w.error_message && (
                      <div className="mt-1 flex items-start gap-1 text-[11px] text-[var(--color-danger)]">
                        <AlertTriangle size={11} className="mt-0.5 shrink-0" />
                        <span className="max-w-xs">{w.error_message}</span>
                      </div>
                    )}
                  </td>
                  <td className="mono px-4 py-3 text-[11px] text-[var(--color-ink-faint)]">
                    {w.service_endpoint ?? "—"}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end gap-1">
                      {w.status === "failed" && (
                        <button
                          className="flex h-6 w-6 items-center justify-center rounded-md text-[var(--color-ink-faint)] hover:bg-[var(--color-idle-soft)]"
                          title="重试部署"
                          onClick={() => redeployMutation.mutate(w.id)}
                          disabled={redeployMutation.isPending}
                        >
                          <RefreshCw size={13} className={redeployMutation.isPending ? "animate-spin" : ""} />
                        </button>
                      )}
                      <button
                        className="flex h-6 w-6 items-center justify-center rounded-md text-[var(--color-ink-faint)] hover:bg-[var(--color-danger-soft)] hover:text-[var(--color-danger)]"
                        title="删除"
                        onClick={() => removeMutation.mutate(w.id)}
                      >
                        <X size={13} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showCreate && <CreateWorkloadModal onClose={() => setShowCreate(false)} />}
    </div>
  );
}

function CreateWorkloadModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const { data: clusters } = useQuery({ queryKey: ["clusters"], queryFn: api.clusters.list });

  const [name, setName] = useState("");
  const [clusterId, setClusterId] = useState("");
  const [namespace, setNamespace] = useState("default");
  const [modelId, setModelId] = useState("");
  const [gpuCount, setGpuCount] = useState("1");
  const [replicas, setReplicas] = useState("1");
  const [error, setError] = useState<string | null>(null);

  const createMutation = useMutation({
    mutationFn: () =>
      api.aiWorkloads.create({
        name,
        cluster_id: clusterId,
        namespace,
        model_id: modelId,
        gpu_count: Number(gpuCount) || 1,
        replicas: Number(replicas) || 1,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ai-workloads"] });
      onClose();
    },
    onError: (e: Error) => setError(e instanceof ApiError ? e.message : "创建失败"),
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md rounded-xl bg-[var(--color-surface)] p-5 shadow-xl">
        <h3 className="mb-3 text-sm font-bold">部署 vLLM 推理服务</h3>
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            setError(null);
            createMutation.mutate();
          }}
        >
          <div>
            <label className="label">名称</label>
            <input className="input" required placeholder="qwen-7b" value={name} onChange={(e) => setName(e.target.value)} />
          </div>

          <div>
            <label className="label">目标集群</label>
            <select className="input" required value={clusterId} onChange={(e) => setClusterId(e.target.value)}>
              <option value="" disabled>
                选一个已建好的集群
              </option>
              {(clusters ?? []).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
            <p className="mt-1 text-[10px] text-[var(--color-ink-faint)]">
              集群控制面必须已经 Ready（kubeconfig 已生成），否则部署会失败——可以之后重试。
            </p>
          </div>

          <div>
            <label className="label">目标命名空间</label>
            <input className="input" value={namespace} onChange={(e) => setNamespace(e.target.value)} />
          </div>

          <div>
            <label className="label">模型（HuggingFace 引用）</label>
            <input
              className="input mono"
              required
              placeholder="Qwen/Qwen2.5-7B-Instruct"
              value={modelId}
              onChange={(e) => setModelId(e.target.value)}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">GPU 数量 / 副本</label>
              <input className="input" type="number" min={1} value={gpuCount} onChange={(e) => setGpuCount(e.target.value)} />
            </div>
            <div>
              <label className="label">副本数</label>
              <input className="input" type="number" min={1} value={replicas} onChange={(e) => setReplicas(e.target.value)} />
            </div>
          </div>

          {error && <p className="text-xs text-[var(--color-danger)]">{error}</p>}

          <div className="mt-1 flex justify-end gap-2">
            <button type="button" className="btn btn-secondary" onClick={onClose}>
              取消
            </button>
            <button type="submit" className="btn btn-primary" disabled={createMutation.isPending}>
              {createMutation.isPending ? "部署中..." : "部署"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
