import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Boxes, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";
import { EmptyState } from "../../components/ui/EmptyState";
import { Modal } from "../../components/ui/Modal";
import { StatusTag } from "../../components/ui/StatusTag";
import type { ClusterCreate } from "../../lib/types";
import { useLanguage } from "../../lib/i18n";

type TranslationKey = Parameters<ReturnType<typeof useLanguage>["t"]>[0];

export default function ClusterList() {
  const { t } = useLanguage();
  const qc = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const { data: clusters, isLoading } = useQuery({ queryKey: ["clusters"], queryFn: api.clusters.list });

  const removeMutation = useMutation({
    mutationFn: (id: string) => api.clusters.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["clusters"] }),
  });

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <p className="text-xs text-[var(--color-ink-muted)]">{t("cl.hint")}</p>
        <button className="btn btn-primary" onClick={() => setShowCreate(true)}>
          <Plus size={14} /> {t("cl.newCluster")}
        </button>
      </div>

      <div className="card overflow-hidden">
        {isLoading ? (
          <div className="p-10 text-center text-xs text-[var(--color-ink-faint)]">{t("cl.loading")}</div>
        ) : !clusters || clusters.length === 0 ? (
          <EmptyState
            icon={Boxes}
            title={t("cl.emptyTitle")}
            hint={t("cl.emptyHint")}
            action={
              <button className="btn btn-primary mt-2" onClick={() => setShowCreate(true)}>
                <Plus size={14} /> {t("cl.newCluster")}
              </button>
            }
          />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--color-border)] text-left text-xs text-[var(--color-ink-muted)]">
                <th className="px-4 py-2.5 font-medium">{t("cl.colName")}</th>
                <th className="px-4 py-2.5 font-medium">{t("cl.colProvider")}</th>
                <th className="px-4 py-2.5 font-medium">{t("cl.colStatus")}</th>
                <th className="px-4 py-2.5 font-medium">{t("cl.colNamespace")}</th>
                <th className="px-4 py-2.5 font-medium">{t("cl.colControlPlaneCount")}</th>
                <th className="px-4 py-2.5 font-medium">{t("cl.colControlPlaneEndpoint")}</th>
                <th className="px-4 py-2.5 font-medium text-right">{t("cl.colActions")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--color-border)]">
              {clusters.map((c) => (
                <tr key={c.id} className="hover:bg-[var(--color-bg)]">
                  <td className="px-4 py-3">
                    <Link to={`/clusters/${c.id}`} className="font-medium text-[var(--color-brand-600)]">
                      {c.name}
                    </Link>
                  </td>
                  <td className="px-4 py-3">
                    <span className="rounded-full bg-[var(--color-idle-soft)] px-2 py-0.5 text-[11px] font-medium text-[var(--color-ink-muted)]">
                      {c.infrastructure_provider}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <StatusTag status={c.status} />
                  </td>
                  <td className="px-4 py-3 text-[var(--color-ink-muted)]">{c.namespace}</td>
                  <td className="px-4 py-3 text-[var(--color-ink-muted)]">{c.control_plane_count}</td>
                  <td className="mono px-4 py-3 text-xs text-[var(--color-ink-muted)]">
                    {c.control_plane_endpoint ?? "—"}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      className="btn-ghost btn !p-1.5"
                      title={t("cl.delete")}
                      onClick={() => {
                        if (confirm(t("cl.confirmDelete", { name: c.name }))) {
                          removeMutation.mutate(c.id);
                        }
                      }}
                    >
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {showCreate && <CreateClusterModal onClose={() => setShowCreate(false)} />}
    </div>
  );
}

const PROVIDERS: { value: NonNullable<ClusterCreate["infrastructure_provider"]>; labelKey: TranslationKey; hintKey: TranslationKey }[] = [
  { value: "metal3", labelKey: "cl.providerMetal3", hintKey: "cl.providerMetal3Hint" },
  { value: "openstack", labelKey: "cl.providerOpenstack", hintKey: "cl.providerOpenstackHint" },
  { value: "vsphere", labelKey: "cl.providerVsphere", hintKey: "cl.providerVsphereHint" },
  { value: "kubevirt", labelKey: "cl.providerKubevirt", hintKey: "cl.providerKubevirtHint" },
  { value: "docker", labelKey: "cl.providerDocker", hintKey: "cl.providerDockerHint" },
];

function CreateClusterModal({ onClose }: { onClose: () => void }) {
  const { t } = useLanguage();
  const qc = useQueryClient();
  const [form, setForm] = useState<ClusterCreate>({
    name: "",
    namespace: "metal3",
    infrastructure_provider: "metal3",
    control_plane_count: 3,
    control_plane_endpoint: "",
    spec: { pod_cidr: "192.168.0.0/16", service_cidr: "10.96.0.0/12", k8s_version: "v1.29.0" },
  });
  const [error, setError] = useState<string | null>(null);
  const isCloud = form.infrastructure_provider !== "metal3" && form.infrastructure_provider !== undefined;

  const createMutation = useMutation({
    mutationFn: () => api.clusters.create(form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["clusters"] });
      onClose();
    },
    onError: (e: Error) => setError(e.message),
  });

  return (
    <Modal title={t("cl.modalTitle")} onClose={onClose} width={600}>
      <form
        className="flex flex-col gap-3.5"
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          createMutation.mutate();
        }}
      >
        <div>
          <label className="label">{t("cl.clusterName")}</label>
          <input
            className="input"
            required
            placeholder="prod-cluster-01"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
        </div>

        <div>
          <label className="label">{t("cl.deployTarget")}</label>
          <div className="grid grid-cols-2 gap-2">
            {PROVIDERS.map((p) => (
              <button
                key={p.value}
                type="button"
                onClick={() => setForm({ ...form, infrastructure_provider: p.value })}
                className={`rounded-lg border p-2.5 text-left transition ${
                  form.infrastructure_provider === p.value
                    ? "border-[var(--color-brand-500)] bg-[var(--color-brand-50)]"
                    : "border-[var(--color-border-strong)] hover:border-[var(--color-brand-500)]"
                }`}
              >
                <div className="text-xs font-semibold">{t(p.labelKey)}</div>
                <div className="mt-0.5 text-[10px] text-[var(--color-ink-faint)]">{t(p.hintKey)}</div>
              </button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">{t("cl.namespace")}</label>
            <input
              className="input"
              value={form.namespace}
              onChange={(e) => setForm({ ...form, namespace: e.target.value })}
            />
          </div>
          <div>
            <label className="label">{t("cl.controlPlaneNodeCount")}</label>
            <input
              className="input"
              type="number"
              min={1}
              value={form.control_plane_count}
              onChange={(e) => setForm({ ...form, control_plane_count: Number(e.target.value) })}
            />
            {!isCloud && (
              <p className="mt-1 text-[10px] text-[var(--color-ink-faint)]">{t("cl.metal3InitialCountHint")}</p>
            )}
          </div>
        </div>
        <div>
          <label className="label">{t("cl.controlPlaneEndpointVip")}</label>
          <input
            className="input mono"
            placeholder="192.0.2.1"
            value={form.control_plane_endpoint ?? ""}
            onChange={(e) => setForm({ ...form, control_plane_endpoint: e.target.value })}
          />
        </div>

        {isCloud && form.infrastructure_provider !== "docker" && (
          <>
            <div className="grid grid-cols-2 gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-3">
              <div>
                <label className="label">{t("cl.controlPlaneFlavor")}</label>
                <input
                  className="input"
                  required
                  placeholder="m1.large"
                  value={form.control_plane_flavor ?? ""}
                  onChange={(e) => setForm({ ...form, control_plane_flavor: e.target.value })}
                />
              </div>
              <div>
                <label className="label">{t("cl.controlPlaneImage")}</label>
                <input
                  className="input"
                  required
                  placeholder="ubuntu-22.04"
                  value={form.control_plane_image ?? ""}
                  onChange={(e) => setForm({ ...form, control_plane_image: e.target.value })}
                />
              </div>
            </div>

            <WorkerPoolEditor
              pools={form.worker_pools ?? []}
              onChange={(pools) => setForm({ ...form, worker_pools: pools })}
            />

            <ProviderConfigFields
              provider={form.infrastructure_provider as "openstack" | "vsphere" | "kubevirt"}
              spec={form.spec ?? {}}
              onChange={(spec) => setForm({ ...form, spec })}
            />
          </>
        )}

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">{t("cl.podCidr")}</label>
            <input
              className="input mono"
              value={(form.spec?.pod_cidr as string) ?? ""}
              onChange={(e) => setForm({ ...form, spec: { ...form.spec, pod_cidr: e.target.value } })}
            />
          </div>
          <div>
            <label className="label">{t("cl.serviceCidr")}</label>
            <input
              className="input mono"
              value={(form.spec?.service_cidr as string) ?? ""}
              onChange={(e) => setForm({ ...form, spec: { ...form.spec, service_cidr: e.target.value } })}
            />
          </div>
        </div>

        {error && <p className="text-xs text-[var(--color-danger)]">{error}</p>}

        <div className="mt-1 flex justify-end gap-2">
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            {t("cl.cancel")}
          </button>
          <button type="submit" className="btn btn-primary" disabled={createMutation.isPending}>
            {createMutation.isPending ? t("cl.creating") : t("cl.create")}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function ProviderConfigFields({
  provider,
  spec,
  onChange,
}: {
  provider: "openstack" | "vsphere" | "kubevirt";
  spec: Record<string, unknown>;
  onChange: (spec: Record<string, unknown>) => void;
}) {
  const { t } = useLanguage();
  // Every field the CAPO/CAPV/CAPK templates read off `cluster.<provider>.*`
  // falls back to `default('')` rather than crashing when missing -- which
  // is exactly why this form existed without them for a while and nobody
  // noticed: an OpenStack/vSphere cluster created without these silently
  // renders manifests with an empty cloudName/server/datacenter instead of
  // erroring, which only fails once it's actually applied against real
  // infrastructure. Collecting them here isn't optional polish.
  const providerSpec = (spec[provider] as Record<string, string>) ?? {};
  const setField = (key: string, value: string) =>
    onChange({ ...spec, [provider]: { ...providerSpec, [key]: value } });

  if (provider === "openstack") {
    return (
      <div className="grid grid-cols-2 gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-3">
        <div>
          <label className="label">{t("cl.cloudName")}</label>
          <input
            className="input"
            required
            placeholder="mycloud"
            value={providerSpec.cloud_name ?? ""}
            onChange={(e) => setField("cloud_name", e.target.value)}
          />
        </div>
        <div>
          <label className="label">{t("cl.externalNetworkId")}</label>
          <input
            className="input mono"
            placeholder="ext-net-uuid"
            value={providerSpec.external_network_id ?? ""}
            onChange={(e) => setField("external_network_id", e.target.value)}
          />
        </div>
      </div>
    );
  }

  if (provider === "vsphere") {
    return (
      <div className="grid grid-cols-2 gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-3">
        <div>
          <label className="label">{t("cl.vcenterServer")}</label>
          <input
            className="input"
            required
            placeholder="vcenter.local"
            value={providerSpec.server ?? ""}
            onChange={(e) => setField("server", e.target.value)}
          />
        </div>
        <div>
          <label className="label">{t("cl.datacenter")}</label>
          <input
            className="input"
            required
            value={providerSpec.datacenter ?? ""}
            onChange={(e) => setField("datacenter", e.target.value)}
          />
        </div>
        <div>
          <label className="label">{t("cl.datastore")}</label>
          <input
            className="input"
            required
            value={providerSpec.datastore ?? ""}
            onChange={(e) => setField("datastore", e.target.value)}
          />
        </div>
        <div>
          <label className="label">{t("cl.network")}</label>
          <input
            className="input"
            required
            value={providerSpec.network ?? ""}
            onChange={(e) => setField("network", e.target.value)}
          />
        </div>
      </div>
    );
  }

  // kubevirt
  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-3">
      <label className="label">{t("cl.storageClass")}</label>
      <input
        className="input"
        required
        placeholder="rook-ceph-block"
        value={providerSpec.storage_class_name ?? ""}
        onChange={(e) => setField("storage_class_name", e.target.value)}
      />
    </div>
  );
}

function WorkerPoolEditor({
  pools,
  onChange,
}: {
  pools: NonNullable<ClusterCreate["worker_pools"]>;
  onChange: (pools: NonNullable<ClusterCreate["worker_pools"]>) => void;
}) {
  const { t } = useLanguage();
  const addPool = () =>
    onChange([...pools, { name: `pool${pools.length + 1}`, count: 1, flavor: "", image: "" }]);

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <label className="label !mb-0">{t("cl.workerPools")}</label>
        <button type="button" className="btn btn-secondary !py-1 !text-[11px]" onClick={addPool}>
          <Plus size={12} /> {t("cl.addPool")}
        </button>
      </div>
      {pools.length === 0 ? (
        <p className="text-[11px] text-[var(--color-ink-faint)]">{t("cl.noPoolsHint")}</p>
      ) : (
        pools.map((pool, i) => (
          <div key={i} className="grid grid-cols-[1fr_70px_1fr_1fr_28px] gap-1.5">
            <input
              className="input !text-xs"
              placeholder={t("cl.poolNamePlaceholder")}
              value={pool.name}
              onChange={(e) => {
                const next = [...pools];
                next[i] = { ...pool, name: e.target.value };
                onChange(next);
              }}
            />
            <input
              className="input !text-xs"
              type="number"
              min={1}
              placeholder={t("cl.poolCountPlaceholder")}
              value={pool.count}
              onChange={(e) => {
                const next = [...pools];
                next[i] = { ...pool, count: Number(e.target.value) };
                onChange(next);
              }}
            />
            <input
              className="input !text-xs"
              placeholder="flavor"
              value={pool.flavor ?? ""}
              onChange={(e) => {
                const next = [...pools];
                next[i] = { ...pool, flavor: e.target.value };
                onChange(next);
              }}
            />
            <input
              className="input !text-xs"
              placeholder="image"
              value={pool.image ?? ""}
              onChange={(e) => {
                const next = [...pools];
                next[i] = { ...pool, image: e.target.value };
                onChange(next);
              }}
            />
            <button
              type="button"
              className="btn-ghost btn !p-1"
              onClick={() => onChange(pools.filter((_, idx) => idx !== i))}
            >
              <Trash2 size={13} />
            </button>
          </div>
        ))
      )}
    </div>
  );
}
