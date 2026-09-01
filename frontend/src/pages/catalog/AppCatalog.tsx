import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Package, Plus, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { api } from "../../lib/api";
import { EmptyState } from "../../components/ui/EmptyState";
import { useLanguage } from "../../lib/i18n";
import { ADDON_ICONS, DEFAULT_ADDON_ICON } from "../../lib/addonIcons";
import type { AddonCatalogItem } from "../../lib/types";

type TranslationKey = Parameters<ReturnType<typeof useLanguage>["t"]>[0];

const CATEGORY_LABEL_KEYS: Record<string, TranslationKey> = {
  networking: "catalog.category.networking",
  storage: "catalog.category.storage",
  platform: "catalog.category.platform",
  observability: "catalog.category.observability",
  compute: "catalog.category.compute",
};

export default function AppCatalog() {
  const { t } = useLanguage();
  const qc = useQueryClient();
  const [category, setCategory] = useState<string>("all");
  const [search, setSearch] = useState("");
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

  const localizedName = (entry: AddonCatalogItem) => t(`addon.${entry.name}.name` as TranslationKey);
  const localizedDesc = (entry: AddonCatalogItem) => t(`addon.${entry.name}.desc` as TranslationKey);

  const categories = useMemo(() => {
    const present = Array.from(new Set((items ?? []).map((c) => c.category)));
    return ["all", ...present];
  }, [items]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return (items ?? []).filter((c) => {
      if (category !== "all" && c.category !== category) return false;
      if (!q) return true;
      return (
        localizedName(c).toLowerCase().includes(q) ||
        localizedDesc(c).toLowerCase().includes(q) ||
        c.name.toLowerCase().includes(q)
      );
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, category, search, t]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-2xl text-xs text-[var(--color-ink-muted)]">{t("catalog.subtitle")}</p>
        <select className="input !w-64" value={clusterId} onChange={(e) => setClusterId(e.target.value)}>
          <option value="">{t("catalog.selectClusterPlaceholder")}</option>
          {(clusters ?? []).map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-[220px] flex-1">
          <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-ink-faint)]" />
          <input
            className="input !pl-9"
            placeholder={t("catalog.search")}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div className="flex flex-wrap gap-1.5">
          {categories.map((c) => (
            <button
              key={c}
              onClick={() => setCategory(c)}
              className={`rounded-full px-3 py-1.5 text-xs font-medium transition ${
                category === c
                  ? "bg-[var(--color-brand-500)] text-white"
                  : "bg-[var(--color-idle-soft)] text-[var(--color-ink-muted)] hover:text-[var(--color-ink)]"
              }`}
            >
              {c === "all" ? t("catalog.allCategories") : t(CATEGORY_LABEL_KEYS[c] ?? "catalog.category.platform")}
            </button>
          ))}
        </div>
      </div>

      {!isLoading && items && (
        <p className="text-[11px] text-[var(--color-ink-faint)]">{t("catalog.resultsCount", { count: filtered.length })}</p>
      )}

      {isLoading ? (
        <p className="text-xs text-[var(--color-ink-faint)]">{t("catalog.loading")}</p>
      ) : filtered.length === 0 ? (
        <div className="card">
          <EmptyState icon={Package} title={t("catalog.empty")} hint={t("catalog.emptyHint")} />
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {filtered.map((entry) => {
            const { icon: Icon, color } = ADDON_ICONS[entry.name] ?? DEFAULT_ADDON_ICON;
            return (
              <div key={entry.name} className="card flex flex-col gap-3 p-4 transition hover:shadow-md">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-3">
                    <div
                      className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-white shadow-sm"
                      style={{ backgroundColor: color }}
                    >
                      <Icon size={20} strokeWidth={2} />
                    </div>
                    <div>
                      <div className="text-sm font-bold leading-tight">{localizedName(entry)}</div>
                      <span className="mono text-[10px] text-[var(--color-ink-faint)]">{entry.name}</span>
                    </div>
                  </div>
                  {clusterId &&
                    (entry.enabled ? (
                      <span className="flex shrink-0 items-center gap-1 rounded-full bg-[var(--color-success-soft)] px-2 py-0.5 text-[10px] font-semibold text-[var(--color-success)]">
                        <Check size={10} /> {t("catalog.installed")}
                      </span>
                    ) : (
                      <span className="shrink-0 rounded-full bg-[var(--color-idle-soft)] px-2 py-0.5 text-[10px] font-semibold text-[var(--color-ink-faint)]">
                        {t("catalog.notInstalled")}
                      </span>
                    ))}
                </div>
                <p className="line-clamp-4 text-xs leading-relaxed text-[var(--color-ink-muted)]">{localizedDesc(entry)}</p>
                {clusterId && (
                  <button
                    className={entry.enabled ? "btn btn-secondary mt-1" : "btn btn-primary mt-1"}
                    disabled={enableMutation.isPending || disableMutation.isPending}
                    onClick={() =>
                      entry.enabled ? disableMutation.mutate(entry.name) : enableMutation.mutate(entry.name)
                    }
                  >
                    {entry.enabled ? (
                      t("catalog.uninstall")
                    ) : (
                      <>
                        <Plus size={13} /> {t("catalog.install")}
                      </>
                    )}
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
