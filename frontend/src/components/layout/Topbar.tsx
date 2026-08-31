import { LogOut, RefreshCw, User } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../../lib/auth";

const TITLES: Record<string, string> = {
  "/": "概览",
  "/clusters": "集群管理",
  "/hardware-assets": "硬件资产",
  "/baremetal-hosts": "裸金属主机",
  "/deployments": "部署任务",
  "/app-catalog": "应用目录",
  "/llm-providers": "LLM 凭证",
  "/ai-workloads": "AI 工作负载",
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
  const segment = "/" + (pathname.split("/")[1] ?? "");
  const title = TITLES[segment] ?? TITLES[pathname] ?? "详情";

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
          API {healthy ? "在线" : "离线"}
        </div>
        <button
          onClick={() => refetch()}
          className="flex h-7 w-7 items-center justify-center rounded-md text-[var(--color-ink-muted)] hover:bg-[var(--color-idle-soft)]"
          aria-label="刷新"
        >
          <RefreshCw size={14} className={isFetching ? "animate-spin" : ""} />
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
            aria-label="退出登录"
            title="退出登录"
          >
            <LogOut size={14} />
          </button>
        </div>
      </div>
    </header>
  );
}
