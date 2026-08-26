import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";

export default function LoginPage() {
  const { isAuthenticated, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  if (isAuthenticated) {
    const from = (location.state as { from?: string } | null)?.from ?? "/";
    return <Navigate to={from} replace />;
  }

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(username, password);
      const from = (location.state as { from?: string } | null)?.from ?? "/";
      navigate(from, { replace: true });
    } catch {
      setError("用户名或密码不对");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex h-screen w-screen items-center justify-center bg-[var(--color-navy-950)] px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-[var(--color-brand-500)] text-lg font-bold text-white">
            M3
          </div>
          <div className="text-center">
            <div className="text-lg font-bold text-white">Metal3 控制台</div>
            <div className="text-xs text-[#7b86a8]">登录以继续</div>
          </div>
        </div>

        <form onSubmit={onSubmit} className="card flex flex-col gap-3.5 p-6">
          <div>
            <label className="label">用户名</label>
            <input
              className="input"
              autoFocus
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
            />
          </div>
          <div>
            <label className="label">密码</label>
            <input
              className="input"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
            />
          </div>

          {error && <p className="text-xs text-[var(--color-danger)]">{error}</p>}

          <button type="submit" className="btn btn-primary mt-1 justify-center" disabled={loading}>
            {loading ? "登录中..." : "登录"}
          </button>
        </form>

        <p className="mt-4 text-center text-[11px] text-[#5b6488]">
          首次启动的管理员账号来自服务端启动日志 —— 见 INSTALL.md
        </p>
      </div>
    </div>
  );
}
