import { Link } from "react-router-dom";

export default function NotFound() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 py-24 text-center">
      <p className="text-3xl font-black text-[var(--color-ink-faint)]">404</p>
      <p className="text-sm text-[var(--color-ink-muted)]">这个页面不存在</p>
      <Link to="/" className="btn btn-primary mt-2">
        返回概览
      </Link>
    </div>
  );
}
