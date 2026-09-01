import { Languages, LogOut, RefreshCw, User } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../../lib/auth";
import { useLanguage } from "../../lib/i18n";

type TranslationKey = Parameters<ReturnType<typeof useLanguage>["t"]>[0];

const TITLE_KEYS: Record<string, TranslationKey> = {
  "/": "nav.overview",
  "/clusters": "nav.clusters",
  "/hardware-assets": "nav.hardwareAssets",
  "/baremetal-hosts": "nav.baremetalHosts",
  "/deployments": "nav.deployments",
  "/app-catalog": "nav.appCatalog",
  "/llm-providers": "nav.llmProviders",
  "/ai-workloads": "nav.aiWorkloads",
};

async function pingHealth(): Promise<boolean> {
  try {
    const res = await fetch("/healthz");
    return res.ok;
  } catch {
    return false;
  }
}

export function Topbar() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { username, logout } = useAuth();
  const { t, toggleLang } = useLanguage();
  const segment = "/" + (pathname.split("/")[1] ?? "");
  const titleKey = TITLE_KEYS[segment] ?? TITLE_KEYS[pathname];
  const title = titleKey ? t(titleKey) : t("topbar.title.detail");

  const { data: healthy, refetch, isFetching } = useQuery({
    queryKey: ["health"],
    queryFn: pingHealth,
    refetchInterval: 30_000,
  });

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-[var(--color-border)] bg-[var(--color-surface)] px-6">
      <h1 className="text-[15px] font-semibold text-[var(--color-ink)]">{title}</h1>
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-1.5 text-xs text-[var(--color-ink-muted)]">
          <span
            className={`h-1.5 w-1.5 rounded-full ${healthy ? "bg-[var(--color-success)]" : "bg-[var(--color-danger)]"}`}
          />
          {healthy ? t("topbar.apiOnline") : t("topbar.apiOffline")}
        </div>
        <button
          onClick={() => refetch()}
          className="flex h-7 w-7 items-center justify-center rounded-md text-[var(--color-ink-muted)] hover:bg-[var(--color-idle-soft)]"
          aria-label={t("topbar.refresh")}
          title={t("topbar.refresh")}
        >
          <RefreshCw size={14} className={isFetching ? "animate-spin" : ""} />
        </button>
        <button
          onClick={toggleLang}
          className="flex h-7 items-center gap-1 rounded-md px-2 text-xs font-medium text-[var(--color-ink-muted)] hover:bg-[var(--color-idle-soft)]"
          aria-label={t("lang.toggle")}
          title={t("lang.toggle")}
        >
          <Languages size={14} /> {t("lang.toggle")}
        </button>
        <div className="flex items-center gap-2 border-l border-[var(--color-border)] pl-4">
          <div className="flex items-center gap-1.5 text-xs font-medium text-[var(--color-ink-muted)]">
            <User size={13} /> {username}
          </div>
          <button
            onClick={() => {
              logout();
              navigate("/login", { replace: true });
            }}
            className="flex h-7 w-7 items-center justify-center rounded-md text-[var(--color-ink-muted)] hover:bg-[var(--color-idle-soft)]"
            aria-label={t("topbar.logout")}
            title={t("topbar.logout")}
          >
            <LogOut size={14} />
          </button>
        </div>
      </div>
    </header>
  );
}
