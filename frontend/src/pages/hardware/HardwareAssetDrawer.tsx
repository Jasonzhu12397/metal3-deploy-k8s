import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, KeyRound, RefreshCw, X } from "lucide-react";
import { useEffect, useState } from "react";
import { api, ApiError } from "../../lib/api";
import { CoreMap } from "../../components/ui/CoreMap";
import { StatusTag } from "../../components/ui/StatusTag";
import type { DiskRole, DiskSpec, HardwareAsset, NicRole, NicSpec } from "../../lib/types";
import { useLanguage } from "../../lib/i18n";

const NIC_ROLES: NicRole[] = ["control", "data", "storage", "sriov", "unassigned"];
const DISK_ROLES: DiskRole[] = ["os", "ceph_osd", "ceph_journal", "local_storage", "unassigned"];

export function HardwareAssetDrawer({ assetId, onClose }: { assetId: string; onClose: () => void }) {
  const { t } = useLanguage();
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
                {t("hwd.cpuMemory")}
              </h4>
              <button
                className="btn btn-secondary !py-1 !text-[11px]"
                onClick={() => syncMutation.mutate()}
                disabled={syncMutation.isPending}
              >
                <RefreshCw size={12} className={syncMutation.isPending ? "animate-spin" : ""} />
                {t("hwd.syncFromIronic")}
              </button>
            </div>
            {syncMutation.isError && (
              <p className="mb-2 text-[11px] text-[var(--color-danger)]">{(syncMutation.error as Error).message}</p>
            )}
            <div className="grid grid-cols-3 gap-2 text-xs">
              <Field label={t("hwd.model")} value={asset.cpu_model ?? "—"} />
              <Field label={t("hwd.topology")} value={`${asset.cpu_sockets}×${asset.cpu_cores_per_socket}×${asset.cpu_threads_per_core}t`} />
              <Field label={t("hwd.memory")} value={`${asset.memory_gb} GB`} />
            </div>
            {asset.cpu_sockets > 0 && asset.cpu_cores_per_socket > 0 && (
              <div className="mt-3 rounded-lg bg-[var(--color-bg)] p-3">
                <CoreMap
                  sockets={asset.cpu_sockets}
                  coresPerSocket={asset.cpu_cores_per_socket}
                  threadsPerCore={asset.cpu_threads_per_core}
                  reservedPerSocket={0}
                />
                <p className="mt-2 text-[11px] text-[var(--color-ink-faint)]">{t("hwd.allUsableNote")}</p>
              </div>
            )}
          </section>

          <section>
            <h4 className="mb-2 text-xs font-bold uppercase tracking-wide text-[var(--color-ink-muted)]">
              {t("hwd.nics", { count: nics.length })}
            </h4>
            {nics.length === 0 ? (
              <p className="text-xs text-[var(--color-ink-faint)]">{t("hwd.noNicsYet")}</p>
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
              {t("hwd.disks", { count: disks.length })}
            </h4>
            {disks.length === 0 ? (
              <p className="text-xs text-[var(--color-ink-faint)]">{t("hwd.noDisksYet")}</p>
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

          <GpuSection asset={asset} assetId={assetId} />

          <BmcCredentialsSection asset={asset} assetId={assetId} />
        </div>

        <div className="sticky bottom-0 mt-auto flex justify-end gap-2 border-t border-[var(--color-border)] bg-[var(--color-surface)] px-5 py-3.5">
          <button className="btn btn-secondary" onClick={onClose}>
            {t("hwd.close")}
          </button>
          <button
            className="btn btn-primary"
            disabled={!dirty || saveRolesMutation.isPending}
            onClick={() => saveRolesMutation.mutate()}
          >
            {saveRolesMutation.isPending ? t("hwd.saving") : t("hwd.saveRoles")}
          </button>
        </div>
      </div>
    </div>
  );
}

function GpuSection({ asset, assetId }: { asset: HardwareAsset; assetId: string }) {
  const { t } = useLanguage();
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [gpuModel, setGpuModel] = useState(asset.gpu_model ?? "");
  const [gpuCount, setGpuCount] = useState(String(asset.gpu_count ?? 0));
  const [gpuMemoryGb, setGpuMemoryGb] = useState(asset.gpu_memory_gb ? String(asset.gpu_memory_gb) : "");

  const saveMutation = useMutation({
    mutationFn: () =>
      api.hardwareAssets.update(assetId, {
        gpu_model: gpuModel || null,
        gpu_count: Number(gpuCount) || 0,
        gpu_memory_gb: gpuMemoryGb ? Number(gpuMemoryGb) : null,
      }),
    onSuccess: () => {
      setEditing(false);
      qc.invalidateQueries({ queryKey: ["hardware-asset", assetId] });
      qc.invalidateQueries({ queryKey: ["hardware-assets"] });
    },
  });

  return (
    <section>
      <div className="mb-2 flex items-center justify-between">
        <h4 className="text-xs font-bold uppercase tracking-wide text-[var(--color-ink-muted)]">{t("hwd.gpu")}</h4>
        {!editing && (
          <button className="btn-ghost btn !py-1 !text-[11px]" onClick={() => setEditing(true)}>
            {asset.has_gpu ? t("hwd.edit") : t("hwd.addInfo")}
          </button>
        )}
      </div>

      {!editing &&
        (asset.has_gpu ? (
          <p className="text-xs">
            {asset.gpu_count}× <span className="mono font-medium">{asset.gpu_model}</span>
            {asset.gpu_memory_gb && <span className="text-[var(--color-ink-faint)]">{t("hwd.gpuPerCard", { mem: asset.gpu_memory_gb })}</span>}
          </p>
        ) : (
          <p className="text-xs text-[var(--color-ink-faint)]">{t("hwd.gpuNotRecorded")}</p>
        ))}

      {editing && (
        <form
          className="flex flex-col gap-2 rounded-lg border border-[var(--color-border)] p-3"
          onSubmit={(e) => {
            e.preventDefault();
            saveMutation.mutate();
          }}
        >
          <div>
            <label className="label">{t("hwd.gpuModel")}</label>
            <input
              className="input"
              placeholder="NVIDIA H100 80GB"
              value={gpuModel}
              onChange={(e) => setGpuModel(e.target.value)}
            />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="label">{t("hwd.gpuCount")}</label>
              <input
                className="input"
                type="number"
                min={0}
                value={gpuCount}
                onChange={(e) => setGpuCount(e.target.value)}
              />
            </div>
            <div>
              <label className="label">{t("hwd.gpuMemoryPerCard")}</label>
              <input
                className="input"
                type="number"
                min={0}
                value={gpuMemoryGb}
                onChange={(e) => setGpuMemoryGb(e.target.value)}
              />
            </div>
          </div>
          <div className="flex justify-end gap-2">
            <button type="button" className="btn btn-secondary !py-1 !text-[11px]" onClick={() => setEditing(false)}>
              {t("hwd.cancel")}
            </button>
            <button type="submit" className="btn btn-primary !py-1 !text-[11px]" disabled={saveMutation.isPending}>
              {saveMutation.isPending ? t("hwd.saving") : t("hwd.save")}
            </button>
          </div>
        </form>
      )}
    </section>
  );
}

function BmcCredentialsSection({ asset, assetId }: { asset: HardwareAsset; assetId: string }) {
  const { t } = useLanguage();
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [username, setUsername] = useState(asset.bmc_username ?? "");
  const [password, setPassword] = useState("");

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["hardware-asset", assetId] });
    qc.invalidateQueries({ queryKey: ["hardware-assets"] });
  };

  const setCredsMutation = useMutation({
    mutationFn: () => api.hardwareAssets.setBmcCredentials(assetId, username, password),
    onSuccess: () => {
      setPassword("");
      setEditing(false);
      invalidate();
    },
  });

  const resyncMutation = useMutation({
    mutationFn: () => api.hardwareAssets.resyncBmcSecret(assetId),
  });

  return (
    <section>
      <div className="mb-2 flex items-center justify-between">
        <h4 className="text-xs font-bold uppercase tracking-wide text-[var(--color-ink-muted)]">
          {t("hwd.bmcCredentials")}
        </h4>
        {asset.has_bmc_credentials && !editing && (
          <button
            className="btn btn-secondary !py-1 !text-[11px]"
            onClick={() => resyncMutation.mutate()}
            disabled={resyncMutation.isPending}
            title={t("hwd.resyncTitle")}
          >
            <RefreshCw size={12} className={resyncMutation.isPending ? "animate-spin" : ""} />
            {t("hwd.rebuildSecret")}
          </button>
        )}
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs">
        <Field label={t("hwd.bmcAddress")} value={asset.bmc_address ?? "—"} mono />
        <Field label={t("hwd.bootMac")} value={asset.boot_mac_address ?? "—"} mono />
      </div>

      <div className="mt-2 flex items-center justify-between rounded-lg bg-[var(--color-bg)] px-2.5 py-2">
        <div className="flex items-center gap-2">
          <KeyRound size={13} className="text-[var(--color-ink-faint)]" />
          {asset.has_bmc_credentials ? (
            <span className="flex items-center gap-1 text-xs">
              <Check size={12} className="text-[var(--color-success)]" />
              {t("hwd.encryptedStored")}<span className="mono font-medium">{asset.bmc_username}</span>
            </span>
          ) : (
            <span className="text-xs text-[var(--color-ink-faint)]">{t("hwd.noCredentialsStored")}</span>
          )}
        </div>
        {!editing && (
          <button className="btn-ghost btn !py-1 !text-[11px]" onClick={() => setEditing(true)}>
            {asset.has_bmc_credentials ? t("hwd.update") : t("hwd.set")}
          </button>
        )}
      </div>

      {resyncMutation.isSuccess && (
        <p className="mt-1.5 text-[11px] text-[var(--color-success)]">
          {t("hwd.secretRewritten", { name: resyncMutation.data.secret_name })}
        </p>
      )}
      {resyncMutation.isError && (
        <p className="mt-1.5 text-[11px] text-[var(--color-danger)]">
          {(resyncMutation.error as ApiError).message}
        </p>
      )}

      {editing && (
        <form
          className="mt-2 flex flex-col gap-2 rounded-lg border border-[var(--color-border)] p-3"
          onSubmit={(e) => {
            e.preventDefault();
            setCredsMutation.mutate();
          }}
        >
          <div>
            <label className="label">{t("hwd.username")}</label>
            <input className="input" required value={username} onChange={(e) => setUsername(e.target.value)} />
          </div>
          <div>
            <label className="label">{t("hwd.password")}</label>
            <input
              className="input"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={asset.has_bmc_credentials ? t("hwd.newPasswordPlaceholder") : ""}
            />
          </div>
          <p className="text-[11px] text-[var(--color-ink-faint)]">{t("hwd.bmcSaveHint")}</p>
          {setCredsMutation.isError && (
            <p className="text-[11px] text-[var(--color-danger)]">
              {(setCredsMutation.error as ApiError).message}
            </p>
          )}
          <div className="flex justify-end gap-2">
            <button
              type="button"
              className="btn btn-secondary !py-1 !text-[11px]"
              onClick={() => {
                setEditing(false);
                setPassword("");
              }}
            >
              {t("hwd.cancel")}
            </button>
            <button type="submit" className="btn btn-primary !py-1 !text-[11px]" disabled={setCredsMutation.isPending}>
              {setCredsMutation.isPending ? t("hwd.saving") : t("hwd.save")}
            </button>
          </div>
        </form>
      )}
    </section>
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
