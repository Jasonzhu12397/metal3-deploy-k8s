import {
  Boxes,
  LayoutGrid,
  Package,
  Rocket,
  Server,
  ServerCog,
} from "lucide-react";
import { NavLink } from "react-router-dom";

const NAV = [
  { to: "/", label: "概览", icon: LayoutGrid, end: true },
  { to: "/clusters", label: "集群管理", icon: Boxes },
  { to: "/hardware-assets", label: "硬件资产", icon: ServerCog },
  { to: "/baremetal-hosts", label: "裸金属主机", icon: Server },
  { to: "/deployments", label: "部署任务", icon: Rocket },
  { to: "/app-catalog", label: "应用目录", icon: Package },
];

export function Sidebar() {
  return (
    <aside className="flex h-full w-60 shrink-0 flex-col bg-[var(--color-navy-900)]">
      <div className="flex items-center gap-2.5 px-5 py-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--color-brand-500)] font-bold text-white">
          M3
        </div>
        <div className="leading-tight">
          <div className="text-[13.5px] font-bold text-white">Metal3 控制台</div>
          <div className="text-[11px] text-[#7b86a8]">Bare Metal &amp; K8s</div>
        </div>
      </div>

      <nav className="flex flex-col gap-1 px-3">
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
          >
            <Icon size={16} strokeWidth={2} />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="mt-auto px-5 py-4 text-[11px] text-[#5b6488]">
        基于 metal3-io + Cluster API
      </div>
    </aside>
  );
}
