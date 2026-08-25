import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { api } from "../../lib/api";
import { Modal } from "../../components/ui/Modal";
import { CoreMap } from "../../components/ui/CoreMap";
import { isolatedCpuCount } from "../../lib/cpu";
import type { HardwareAsset } from "../../lib/types";

export function AssignAssetsModal({ clusterId, onClose }: { clusterId: string; onClose: () => void }) {
  const qc = useQueryClient();
  const [poolName, setPoolName] = useState("pool1");
  const [role, setRole] = useState<"worker" | "control-plane">("worker");
  const [selected, setSelected] = useState<string[]>([]);
  const [reservedPerSocket, setReservedPerSocket] = useState(4);
  const [isolationInterrupts, setIsolationInterrupts] = useState(false);
  const [hugepageCount, setHugepageCount] = useState(16);
  const [error, setError] = useState<string | null>(null);

  const { data: assets, isLoading } = useQuery({
    queryKey: ["hardware-assets", "unassigned"],
    queryFn: () => api.hardwareAssets.list({ unassigned_only: true }),
  });

  const assignMutation = useMutation({
    mutationFn: () =>
      api.clusters.assignToPool(clusterId, poolName, {
        asset_ids: selected,
        role,
        reserved_cores_per_socket: reservedPerSocket,
        isolation_interrupts: isolationInterrupts,
        hugepage_count_1gb: hugepageCount,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cluster-pools", clusterId] });
      qc.invalidateQueries({ queryKey: ["hardware-assets"] });
      onClose();
    },
    onError: (e: Error) => setError(e.message),
  });

  const previewAsset = useMemo<HardwareAsset | undefined>(
    () => assets?.find((a) => selected.includes(a.id)),
    [assets, selected],
  );

  const toggle = (id: string) =>
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));

  return (
    <Modal title="分配硬件资产到节点池" onClose={onClose} width={640}>
      <form
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          if (selected.length === 0) {
            setError("至少选一台机器");
            return;
          }
          assignMutation.mutate();
        }}
      >
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">节点池名称</label>
            <input className="input" value={poolName} onChange={(e) => setPoolName(e.target.value)} required />
          </div>
          <div>
            <label className="label">角色</label>
            <select className="input" value={role} onChange={(e) => setRole(e.target.value as typeof role)}>
              <option value="worker">worker</option>
              <option value="control-plane">control-plane</option>
            </select>
          </div>
        </div>

        <div>
          <label className="label">选择空闲硬件（{selected.length} 台已选）</label>
          <div className="max-h-56 overflow-y-auto rounded-lg border border-[var(--color-border)]">
            {isLoading ? (
              <p className="p-4 text-center text-xs text-[var(--color-ink-faint)]">加载中...</p>
            ) : !assets || assets.length === 0 ? (
              <p className="p-4 text-center text-xs text-[var(--color-ink-faint)]">
                没有空闲资产 —— 先注册裸金属主机并等 Ironic 探测完成
              </p>
            ) : (
              <ul className="divide-y divide-[var(--color-border)]">
                {assets.map((a) => (
                  <li key={a.id}>
                    <label className="flex cursor-pointer items-center gap-3 px-3 py-2 hover:bg-[var(--color-bg)]">
                      <input
                        type="checkbox"
                        checked={selected.includes(a.id)}
                        onChange={() => toggle(a.id)}
                      />
                      <div className="flex-1">
                        <div className="text-sm font-medium">{a.name}</div>
                        <div className="text-[11px] text-[var(--color-ink-faint)]">
                          {a.model ?? "未知型号"} · {a.cpu_sockets}×{a.cpu_cores_per_socket}核 · {a.memory_gb}GB
                        </div>
                      </div>
                    </label>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-3.5">
          <div className="mb-2 flex items-center justify-between">
            <label className="label !mb-0">每 Socket 预留核数（CPU 预留）</label>
            <span className="mono text-sm font-semibold text-[var(--color-brand-600)]">{reservedPerSocket}</span>
          </div>
          <input
            type="range"
            min={0}
            max={previewAsset?.cpu_cores_per_socket ?? 16}
            value={reservedPerSocket}
            onChange={(e) => setReservedPerSocket(Number(e.target.value))}
            className="w-full"
          />

          {previewAsset ? (
            <div className="mt-3">
              <CoreMap
                sockets={previewAsset.cpu_sockets}
                coresPerSocket={previewAsset.cpu_cores_per_socket}
                threadsPerCore={previewAsset.cpu_threads_per_core}
                reservedPerSocket={reservedPerSocket}
              />
              <p className="mt-2 text-[11px] text-[var(--color-ink-faint)]">
                业务可用逻辑核：
                <span className="mono font-semibold text-[var(--color-ink)]">
                  {" "}
                  {isolatedCpuCount(
                    previewAsset.cpu_sockets,
                    previewAsset.cpu_cores_per_socket,
                    previewAsset.cpu_threads_per_core,
                    reservedPerSocket,
                  )}
                </span>
                {"  ·  以 "}
                <span className="font-medium">{previewAsset.name}</span>
                {" 的 CPU 拓扑预览（池内所有机器按此规则统一计算）"}
              </p>
            </div>
          ) : (
            <p className="mt-2 text-[11px] text-[var(--color-ink-faint)]">勾选一台机器即可预览核心分配</p>
          )}
        </div>

        <div className="grid grid-cols-2 items-center gap-3">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={isolationInterrupts}
              onChange={(e) => setIsolationInterrupts(e.target.checked)}
            />
            隔离中断（DPDK/CNF 场景建议开启）
          </label>
          <div>
            <label className="label">1GB 大页数量</label>
            <input
              type="number"
              className="input"
              min={0}
              value={hugepageCount}
              onChange={(e) => setHugepageCount(Number(e.target.value))}
            />
          </div>
        </div>

        {error && <p className="text-xs text-[var(--color-danger)]">{error}</p>}

        <div className="flex justify-end gap-2">
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            取消
          </button>
          <button type="submit" className="btn btn-primary" disabled={assignMutation.isPending}>
            {assignMutation.isPending ? "分配中..." : `分配 ${selected.length} 台到 ${poolName}`}
          </button>
        </div>
      </form>
    </Modal>
  );
}
