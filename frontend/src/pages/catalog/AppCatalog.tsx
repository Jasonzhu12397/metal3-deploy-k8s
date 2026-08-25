import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Package, Plus } from "lucide-react";
import { useState } from "react";
import { api } from "../../lib/api";
import { EmptyState } from "../../components/ui/EmptyState";

export default function AppCatalog() {
  const qc = useQueryClient();
  const [category, setCategory] = useState("全部");
  const [clusterId, setClusterId] = useState<string>("");

  const { data: clusters } = useQuery({ queryKey: ["clusters"], queryFn: api.clusters.list });

  // Cluster-agnostic catalog when nothing's selected; the per-cluster
  // endpoint returns the same catalog with `enabled` set relative to that
  // cluster's spec.addons, so switching the dropdown swaps queries rather
  // than post-processing one fixed list against a locally-guessed shape.
  const { data: items, isLoading } = useQuery({
    queryKey: ["addons", clusterId || "catalog"],
    queryFn: () => (clusterId ? api.addons.forCluster(clusterId) : api.addons.catalog()),
  });

  const enableMutation = useMutation({
    mutationFn: (name: string) => api.addons.enable(clusterId, name),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["addons", clusterId] }),
  });
  const disableMutation = useMutation({
    mutationFn: (name: string) => api.addons.disable(clusterId, name),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["addons", clusterId] }),
  });

  const categories = ["全部", ...Array.from(new Set((items ?? []).map((c) => c.category)))];
  const filtered = (items ?? []).filter((c) => category === "全部" || c.category === category);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-[var(--color-ink-muted)]">
          这套平台常用的组件目录，对应集群配置里的 <code className="mono">addons:</code> 段。选一个集群可以直接在这里启用/停用。
        </p>
        <select className="input !w-56" value={clusterId} onChange={(e) => setClusterId(e.target.value)}>
          <option value="">仅浏览目录（不关联集群）</option>
          {(clusters ?? []).map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {categories.map((c) => (
          <button
            key={c}
            onClick={() => setCategory(c)}
            className={`rounded-full px-3 py-1 text-xs font-medium transition ${
              category === c
                ? "bg-[var(--color-brand-500)] text-white"
                : "bg-[var(--color-idle-soft)] text-[var(--color-ink-muted)] hover:text-[var(--color-ink)]"
            }`}
          >
            {c}
          </button>
        ))}
      </div>

      {isLoading ? (
        <p className="text-xs text-[var(--color-ink-faint)]">加载中...</p>
      ) : filtered.length === 0 ? (
        <div className="card">
          <EmptyState icon={Package} title="目录是空的" />
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {filtered.map((entry) => (
            <div key={entry.name} className="card flex flex-col gap-3 p-4">
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2.5">
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[var(--color-navy-900)] text-[10px] font-bold text-white">
                    {entry.icon}
                  </div>
                  <div>
                    <div className="text-sm font-bold leading-tight">{entry.display_name}</div>
                    <span className="mono text-[10px] text-[var(--color-ink-faint)]">{entry.name}</span>
                  </div>
                </div>
                {clusterId &&
                  (entry.enabled ? (
                    <span className="flex shrink-0 items-center gap-1 rounded-full bg-[var(--color-success-soft)] px-2 py-0.5 text-[10px] font-semibold text-[var(--color-success)]">
                      <Check size={10} /> 已启用
                    </span>
                  ) : (
                    <span className="shrink-0 rounded-full bg-[var(--color-idle-soft)] px-2 py-0.5 text-[10px] font-semibold text-[var(--color-ink-faint)]">
                      未配置
                    </span>
                  ))}
              </div>
              <p className="text-xs leading-relaxed text-[var(--color-ink-muted)]">{entry.description}</p>
              {clusterId && (
                <button
                  className={entry.enabled ? "btn btn-secondary mt-1" : "btn btn-primary mt-1"}
                  disabled={enableMutation.isPending || disableMutation.isPending}
                  onClick={() =>
                    entry.enabled ? disableMutation.mutate(entry.name) : enableMutation.mutate(entry.name)
                  }
                >
                  {entry.enabled ? "停用" : (
                    <>
                      <Plus size={13} /> 启用
                    </>
                  )}
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
