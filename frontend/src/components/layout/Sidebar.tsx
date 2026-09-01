import {
  Boxes,
  Cpu,
  LayoutGrid,
  Package,
  Rocket,
  Server,
  ServerCog,
  Sparkles,
} from "lucide-react";
import { NavLink } from "react-router-dom";
import { useLanguage } from "../../lib/i18n";

const NAV = [
  { to: "/", key: "nav.overview" as const, icon: LayoutGrid, end: true },
  { to: "/clusters", key: "nav.clusters" as const, icon: Boxes },
  { to: "/hardware-assets", key: "nav.hardwareAssets" as const, icon: ServerCog },
  { to: "/baremetal-hosts", key: "nav.baremetalHosts" as const, icon: Server },
  { to: "/deployments", key: "nav.deployments" as const, icon: Rocket },
  { to: "/app-catalog", key: "nav.appCatalog" as const, icon: Package },
  { to: "/llm-providers", key: "nav.llmProviders" as const, icon: Cpu },
  { to: "/ai-workloads", key: "nav.aiWorkloads" as const, icon: Sparkles },
];

export function Sidebar() {
  const { t } = useLanguage();
  return (
    <aside className="flex h-full w-60 shrink-0 flex-col bg-[var(--color-navy-900)]">
      <div className="flex items-center gap-2.5 px-5 py-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--color-brand-500)] font-bold text-white">
          M3
        </div>
        <div className="leading-tight">
          <div className="text-[13.5px] font-bold text-white">{t("app.name")}</div>
          <div className="text-[11px] text-[#7b86a8]">{t("sidebar.tagline")}</div>
        </div>
      </div>

      <nav className="flex flex-col gap-1 px-3">
        {NAV.map(({ to, key, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
          >
            <Icon size={16} strokeWidth={2} />
            {t(key)}
          </NavLink>
        ))}
      </nav>

      <div className="mt-auto px-5 py-4 text-[11px] text-[#5b6488]">
        metal3-io + Cluster API
      </div>
    </aside>
  );
}
