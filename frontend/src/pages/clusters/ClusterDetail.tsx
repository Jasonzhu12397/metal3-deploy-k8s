import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileCode2, Layers, Plus, Rocket, Settings2, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../../lib/api";
import { CodeBlock } from "../../components/ui/CodeBlock";
import { CoreMap } from "../../components/ui/CoreMap";
import { EmptyState } from "../../components/ui/EmptyState";
import { StatusTag } from "../../components/ui/StatusTag";
import { AssignAssetsModal } from "./AssignAssetsModal";
import type { HardwareAsset } from "../../lib/types";
import { useLanguage } from "../../lib/i18n";

type TranslationKey = Parameters<ReturnType<typeof useLanguage>["t"]>[0];

const TAB_KEYS: { key: "pools" | "manifests" | "deployments"; labelKey: TranslationKey; icon: typeof Layers }[] = [
  { key: "pools", labelKey: "cd.tabPools", icon: Layers },
  { key: "manifests", labelKey: "cd.tabManifests", icon: FileCode2 },
  { key: "deployments", labelKey: "cd.tabDeployments", icon: Rocket },
];

export default function ClusterDetail() {
  const { t } = useLanguage();
  const { id = "" } = useParams();
  const [tab, setTab] = useState<"pools" | "manifests" | "deployments">("pools");

  const { data: cluster } = useQuery({ queryKey: ["cluster", id], queryFn: () => api.clusters.get(id) });

  // Cloud/CAPD-backed clusters (anything not metal3) have nothing
  // actionable on the "节点池" tab -- no HardwareAsset to pick, just an
  // explanatory notice (see CloudPoolsNotice below). Landing there by
  // default made "发起部署" easy to miss entirely: nothing on that first
  // screen even hints that a different tab has the button. Jump straight
  // to "部署" for these instead. Runs once per cluster id (not on every
  // render) so manually switching tabs afterward still works normally.
  useEffect(() => {
    if (cluster && cluster.infrastructure_provider !== "metal3") {
      setTab("deployments");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, cluster?.infrastructure_provider]);

  if (!cluster) return <p className="text-xs text-[var(--color-ink-faint)]">{t("cd.loading")}</p>;

  const isCloud = cluster.infrastructure_provider !== "metal3";

  return (
    <div className="flex flex-col gap-5">
      <div className="card flex items-center justify-between p-5">
        <div>
          <div className="flex items-center gap-2.5">
            <h2 className="text-lg font-bold">{cluster.name}</h2>
            <StatusTag status={cluster.status} />
            <span className="rounded-full bg-[var(--color-idle-soft)] px-2 py-0.5 text-[11px] font-medium text-[var(--color-ink-muted)]">
              {cluster.infrastructure_provider}
            </span>
          </div>
          <p className="mono mt-1 text-xs text-[var(--color-ink-muted)]">
            {cluster.namespace} · {t("cd.controlPlaneCount", { count: cluster.control_plane_count })} ·{" "}
            {cluster.control_plane_endpoint ?? t("cd.noEndpoint")}
          </p>
        </div>
      </div>

      <div className="flex gap-1 border-b border-[var(--color-border)]">
        {TAB_KEYS.map(({ key, labelKey, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`flex items-center gap-1.5 border-b-2 px-3.5 py-2.5 text-[13px] font-medium transition ${
              tab === key
                ? "border-[var(--color-brand-500)] text-[var(--color-brand-600)]"
                : "border-transparent text-[var(--color-ink-muted)] hover:text-[var(--color-ink)]"
            }`}
          >
            <Icon size={14} /> {t(labelKey)}
          </button>
        ))}
      </div>

      {tab === "pools" && (isCloud ? <CloudPoolsNotice provider={cluster.infrastructure_provider} /> : <PoolsTab clusterId={id} />)}
      {tab === "manifests" && <ManifestsTab clusterId={id} />}
      {tab === "deployments" && <DeploymentsTab clusterId={id} />}
    </div>
  );
}

function CloudPoolsNotice({ provider }: { provider: string }) {
  const { t } = useLanguage();
  return (
    <div className="card p-8 text-center">
      <p className="text-sm font-medium">{t("cd.cloudNoPoolsTitle", { provider })}</p>
      <p className="mx-auto mt-2 max-w-md text-xs text-[var(--color-ink-muted)]">
        {provider === "openstack" && t("cd.cloudNoPoolsOpenstack")}
        {provider === "vsphere" && t("cd.cloudNoPoolsVsphere")}
        {provider === "kubevirt" && t("cd.cloudNoPoolsKubevirt")}
        {provider === "docker" && t("cd.cloudNoPoolsDocker")}
        {t("cd.cloudNoPoolsSuffix")}
      </p>
    </div>
  );
}

function PoolsTab({ clusterId }: { clusterId: string }) {
  const { t } = useLanguage();
  const qc = useQueryClient();
  const [showAssign, setShowAssign] = useState(false);
  const { data: pools, isLoading } = useQuery({
    queryKey: ["cluster-pools", clusterId],
    queryFn: () => api.clusters.pools(clusterId),
  });
  const { data: allAssets } = useQuery({
    queryKey: ["hardware-assets"],
    queryFn: () => api.hardwareAssets.list(),
  });

  const unassignMutation = useMutation({
    mutationFn: ({ pool, assetId }: { pool: string; assetId: string }) =>
      api.clusters.unassignAsset(clusterId, pool, assetId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cluster-pools", clusterId] });
      qc.invalidateQueries({ queryKey: ["hardware-assets"] });
    },
  });

  const assetById = new Map((allAssets ?? []).map((a) => [a.id, a]));
  const poolEntries = Object.entries(pools ?? {});

  return (
    <div className="flex flex-col gap-4">
      <div className="flex justify-end">
        <button className="btn btn-primary" onClick={() => setShowAssign(true)}>
          <Plus size={14} /> {t("cd.assignHardwareToPool")}
        </button>
      </div>

      {isLoading ? (
        <p className="text-xs text-[var(--color-ink-faint)]">{t("cd.loading")}</p>
      ) : poolEntries.length === 0 ? (
        <div className="card">
          <EmptyState
            icon={Layers}
            title={t("cd.noPoolsTitle")}
            hint={t("cd.noPoolsHint")}
            action={
              <button className="btn btn-primary mt-2" onClick={() => setShowAssign(true)}>
                <Plus size={14} /> {t("cd.assignHardwareToPool")}
              </button>
            }
          />
        </div>
      ) : (
        poolEntries.map(([poolName, assignments]) => {
          const isControlPlane = assignments[0]?.role === "control-plane";
          return (
          <div key={poolName} className="card p-5">
            <div className="mb-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold">{poolName}</h3>
                <span className="rounded-full bg-[var(--color-idle-soft)] px-2 py-0.5 text-[11px] font-medium text-[var(--color-ink-muted)]">
                  {assignments[0]?.role ?? "worker"}
                </span>
                <span className="text-xs text-[var(--color-ink-faint)]">{t("cd.machineCount", { count: assignments.length })}</span>
                {isControlPlane && (
                  <span className="text-[11px] text-[var(--color-ink-faint)]">
                    {t("cd.controlPlaneDriverNote")}
                    {assignments.length === 1 && t("cd.singleNodeNote")}
                  </span>
                )}
              </div>
            </div>
            <ul className="flex flex-col gap-3">
              {assignments.map((a) => {
                const asset = assetById.get(a.asset_id) as HardwareAsset | undefined;
                return (
                  <li
                    key={a.id}
                    className="flex flex-col gap-2 rounded-lg border border-[var(--color-border)] p-3 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div>
                      <div className="text-sm font-medium">{asset?.name ?? a.asset_id.slice(0, 8)}</div>
                      <div className="mono mt-0.5 text-[11px] text-[var(--color-ink-faint)]">
                        reserved_cpus: {a.computed_reserved_cpus || "—"}
                      </div>
                      <div className="mt-0.5 text-[11px] text-[var(--color-ink-faint)]">
                        {t("cd.isolatedCoresNote", { count: a.computed_isolated_cpu_count, type: a.hugepage_type, n: a.hugepage_count_1gb })}
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      {asset && (
                        <CoreMap
                          compact
                          sockets={asset.cpu_sockets}
                          coresPerSocket={asset.cpu_cores_per_socket}
                          threadsPerCore={asset.cpu_threads_per_core}
                          reservedPerSocket={a.reserved_cores_per_socket}
                        />
                      )}
                      <button
                        className="btn-ghost btn !p-1.5"
                        title={t("cd.removeFromPool")}
                        onClick={() => unassignMutation.mutate({ pool: poolName, assetId: a.asset_id })}
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
          );
        })
      )}

      {showAssign && <AssignAssetsModal clusterId={clusterId} onClose={() => setShowAssign(false)} />}
    </div>
  );
}

function ManifestsTab({ clusterId }: { clusterId: string }) {
  const { t } = useLanguage();
  const [activeYaml, setActiveYaml] = useState<"bmh" | "cluster" | string>("bmh");

  const generateMutation = useMutation({
    mutationFn: () => api.clusters.generateManifests(clusterId),
  });

  const bundle = generateMutation.data;

  return (
    <div className="flex flex-col gap-4">
      <div className="card flex items-center justify-between p-4">
        <p className="text-xs text-[var(--color-ink-muted)]">{t("cd.manifestsHint")}</p>
        <button className="btn btn-primary shrink-0" onClick={() => generateMutation.mutate()}>
          <Settings2 size={14} /> {generateMutation.isPending ? t("cd.generating") : t("cd.generateManifests")}
        </button>
      </div>

      {generateMutation.isError && (
        <p className="text-xs text-[var(--color-danger)]">{(generateMutation.error as Error).message}</p>
      )}

      {bundle && (
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap gap-1.5">
            <TabPill active={activeYaml === "bmh"} onClick={() => setActiveYaml("bmh")} label="bmh.yaml" />
            <TabPill
              active={activeYaml === "cluster"}
              onClick={() => setActiveYaml("cluster")}
              label={t("cd.clusterConfigTab")}
            />
            {Object.keys(bundle.network_policies).map((key) => (
              <TabPill key={key} active={activeYaml === key} onClick={() => setActiveYaml(key)} label={key} />
            ))}
          </div>
          <CodeBlock
            code={
              activeYaml === "bmh"
                ? bundle.bmh_yaml
                : activeYaml === "cluster"
                  ? bundle.cluster_config_yaml
                  : (bundle.network_policies[activeYaml] ?? "")
            }
          />
        </div>
      )}
    </div>
  );
}

function TabPill({ active, onClick, label }: { active: boolean; onClick: () => void; label: string }) {
  return (
    <button
      onClick={onClick}
      className={`mono rounded-md px-2.5 py-1 text-[11px] font-medium transition ${
        active
          ? "bg-[var(--color-brand-500)] text-white"
          : "bg-[var(--color-idle-soft)] text-[var(--color-ink-muted)] hover:text-[var(--color-ink)]"
      }`}
    >
      {label}
    </button>
  );
}

function DeploymentsTab({ clusterId }: { clusterId: string }) {
  const { t } = useLanguage();
  const qc = useQueryClient();
  const { data: deployments, isLoading } = useQuery({
    queryKey: ["deployments", clusterId],
    queryFn: () => api.deployments.list(clusterId),
  });

  const startMutation = useMutation({
    mutationFn: () => api.deployments.create(clusterId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["deployments", clusterId] }),
  });

  return (
    <div className="flex flex-col gap-4">
      <div className="flex justify-end">
        <button className="btn btn-primary" onClick={() => startMutation.mutate()} disabled={startMutation.isPending}>
          <Rocket size={14} /> {startMutation.isPending ? t("cd.startingDeployment") : t("cd.startDeployment")}
        </button>
      </div>
      {startMutation.isError && (
        <p className="text-xs text-[var(--color-danger)]">{(startMutation.error as Error).message}</p>
      )}

      <div className="card overflow-hidden">
        {isLoading ? (
          <p className="p-8 text-center text-xs text-[var(--color-ink-faint)]">{t("cd.loading")}</p>
        ) : !deployments || deployments.length === 0 ? (
          <EmptyState icon={Rocket} title={t("cd.notDeployedYetTitle")} hint={t("cd.notDeployedYetHint")} />
        ) : (
          <ul className="divide-y divide-[var(--color-border)]">
            {deployments.map((d) => (
              <li key={d.id} className="flex items-center justify-between px-4 py-3">
                <Link to={`/deployments/${d.id}`} className="mono text-sm font-medium hover:text-[var(--color-brand-600)]">
                  {d.id}
                </Link>
                <StatusTag status={d.phase} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
