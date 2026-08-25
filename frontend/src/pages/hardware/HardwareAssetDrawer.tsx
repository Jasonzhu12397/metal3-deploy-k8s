import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw, X } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { CoreMap } from "../../components/ui/CoreMap";
import { StatusTag } from "../../components/ui/StatusTag";
import type { DiskRole, DiskSpec, NicRole, NicSpec } from "../../lib/types";

const NIC_ROLES: NicRole[] = ["control", "data", "storage", "sriov", "unassigned"];
const DISK_ROLES: DiskRole[] = ["os", "ceph_osd", "ceph_journal", "local_storage", "unassigned"];

export function HardwareAssetDrawer({ assetId, onClose }: { assetId: string; onClose: () => void }) {
  const qc = useQueryClient();
  const { data: asset } = useQuery({
    queryKey: ["hardware-asset", assetId],
    queryFn: () => api.hardwareAssets.get(assetId),
  });

  const [nics, setNics] = useState<NicSpec[]>([]);
  const [disks, setDisks] = useState<DiskSpec[]>([]);

  useEffect(() => {
    if (asset) {
      setNics(asset.nics);
      setDisks(asset.disks);
    }
  }, [asset]);

  const syncMutation = useMutation({
    mutationFn: () => api.hardwareAssets.syncFromIronic(assetId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["hardware-asset", assetId] });
      qc.invalidateQueries({ queryKey: ["hardware-assets"] });
    },
  });

  const saveRolesMutation = useMutation({
    mutationFn: () => api.hardwareAssets.update(assetId, { nics, disks }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["hardware-asset", assetId] });
      qc.invalidateQueries({ queryKey: ["hardware-assets"] });
    },
  });

  if (!asset) return null;

  const dirty = JSON.stringify(nics) !== JSON.stringify(asset.nics) || JSON.stringify(disks) !== JSON.stringify(asset.disks);

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-[rgba(16,21,42,0.45)]">
      <div className="flex h-full w-full max-w-lg flex-col overflow-y-auto bg-[var(--color-surface)] shadow-2xl">
        <div className="flex items-center justify-between border-b border-[var(--color-border)] px-5 py-4">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-bold">{asset.name}</h3>
              <StatusTag status={asset.status} />
            </div>
            <p className="text-[11px] text-[var(--color-ink-faint)]">{asset.vendor} {asset.model}</p>
          </div>
          <button onClick={onClose} className="btn-ghost btn !p-1.5">
            <X size={16} />
          </button>
        </div>

        <div className="flex flex-col gap-6 p-5">
          <section>
            <div className="mb-2 flex items-center justify-between">
              <h4 className="text-xs font-bold uppercase tracking-wide text-[var(--color-ink-muted)]">
                CPU / 内存
              </h4>
              <button
                className="btn btn-secondary !py-1 !text-[11px]"
                onClick={() => syncMutation.mutate()}
                disabled={syncMutation.isPending}
              >
                <RefreshCw size={12} className={syncMutation.isPending ? "animate-spin" : ""} />
                从 Ironic 同步
              </button>
            </div>
            {syncMutation.isError && (
              <p className="mb-2 text-[11px] text-[var(--color-danger)]">{(syncMutation.error as Error).message}</p>
            )}
            <div className="grid grid-cols-3 gap-2 text-xs">
              <Field label="型号" value={asset.cpu_model ?? "—"} />
              <Field label="拓扑" value={`${asset.cpu_sockets}×${asset.cpu_cores_per_socket}×${asset.cpu_threads_per_core}t`} />
              <Field label="内存" value={`${asset.memory_gb} GB`} />
            </div>
            {asset.cpu_sockets > 0 && asset.cpu_cores_per_socket > 0 && (
              <div className="mt-3 rounded-lg bg-[var(--color-bg)] p-3">
                <CoreMap
                  sockets={asset.cpu_sockets}
                  coresPerSocket={asset.cpu_cores_per_socket}
                  threadsPerCore={asset.cpu_threads_per_core}
                  reservedPerSocket={0}
                />
                <p className="mt-2 text-[11px] text-[var(--color-ink-faint)]">
                  全部标记为"业务可用" —— 实际预留数由分配到的节点池决定
                </p>
              </div>
            )}
          </section>

          <section>
            <h4 className="mb-2 text-xs font-bold uppercase tracking-wide text-[var(--color-ink-muted)]">
              网卡（{nics.length}）
            </h4>
            {nics.length === 0 ? (
              <p className="text-xs text-[var(--color-ink-faint)]">还没有网卡数据，先从 Ironic 同步</p>
            ) : (
              <ul className="flex flex-col gap-2">
                {nics.map((nic, i) => (
                  <li
                    key={i}
                    className="flex items-center justify-between gap-3 rounded-lg border border-[var(--color-border)] p-2.5"
                  >
                    <div className="min-w-0">
                      <div className="mono truncate text-xs font-medium">
                        {nic.pci_address || nic.kernel_name || `nic-${i}`}
                      </div>
                      <div className="truncate text-[11px] text-[var(--color-ink-faint)]">
                        {nic.kernel_name ?? "—"} {nic.model ? `· ${nic.model}` : ""}
                        {nic.speed_gbps ? ` · ${nic.speed_gbps}Gbps` : ""}
                      </div>
                    </div>
                    <select
                      className="input !w-32 shrink-0"
                      value={nic.role}
                      onChange={(e) => {
                        const next = [...nics];
                        next[i] = { ...nic, role: e.target.value as NicRole };
                        setNics(next);
                      }}
                    >
                      {NIC_ROLES.map((r) => (
                        <option key={r} value={r}>
                          {r}
                        </option>
                      ))}
                    </select>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section>
            <h4 className="mb-2 text-xs font-bold uppercase tracking-wide text-[var(--color-ink-muted)]">
              磁盘（{disks.length}）
            </h4>
            {disks.length === 0 ? (
              <p className="text-xs text-[var(--color-ink-faint)]">还没有磁盘数据，先从 Ironic 同步</p>
            ) : (
              <ul className="flex flex-col gap-2">
                {disks.map((disk, i) => (
                  <li
                    key={i}
                    className="flex items-center justify-between gap-3 rounded-lg border border-[var(--color-border)] p-2.5"
                  >
                    <div className="min-w-0">
                      <div className="truncate text-xs font-medium">{disk.model ?? disk.device ?? `disk-${i}`}</div>
                      <div className="text-[11px] text-[var(--color-ink-faint)]">
                        {disk.media_type} {disk.size_gb ? `· ${disk.size_gb} GB` : ""}
                      </div>
                    </div>
                    <select
                      className="input !w-32 shrink-0"
                      value={disk.role}
                      onChange={(e) => {
                        const next = [...disks];
                        next[i] = { ...disk, role: e.target.value as DiskRole };
                        setDisks(next);
                      }}
                    >
                      {DISK_ROLES.map((r) => (
                        <option key={r} value={r}>
                          {r}
                        </option>
                      ))}
                    </select>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="grid grid-cols-2 gap-2 text-xs">
            <Field label="BMC 地址" value={asset.bmc_address ?? "—"} mono />
            <Field label="Boot MAC" value={asset.boot_mac_address ?? "—"} mono />
          </section>
        </div>

        <div className="sticky bottom-0 mt-auto flex justify-end gap-2 border-t border-[var(--color-border)] bg-[var(--color-surface)] px-5 py-3.5">
          <button className="btn btn-secondary" onClick={onClose}>
            关闭
          </button>
          <button
            className="btn btn-primary"
            disabled={!dirty || saveRolesMutation.isPending}
            onClick={() => saveRolesMutation.mutate()}
          >
            {saveRolesMutation.isPending ? "保存中..." : "保存角色分配"}
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="rounded-lg bg-[var(--color-bg)] px-2.5 py-2">
      <div className="text-[10px] font-medium uppercase tracking-wide text-[var(--color-ink-faint)]">{label}</div>
      <div className={`truncate text-xs font-medium ${mono ? "mono" : ""}`}>{value}</div>
    </div>
  );
}
