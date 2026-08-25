import type { LucideIcon } from "lucide-react";

export function EmptyState({
  icon: Icon,
  title,
  hint,
  action,
}: {
  icon: LucideIcon;
  title: string;
  hint?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-16 text-center">
      <div className="mb-1 flex h-11 w-11 items-center justify-center rounded-full bg-[var(--color-idle-soft)]">
        <Icon size={20} className="text-[var(--color-ink-faint)]" />
      </div>
      <p className="text-sm font-medium text-[var(--color-ink)]">{title}</p>
      {hint && <p className="max-w-sm text-xs text-[var(--color-ink-muted)]">{hint}</p>}
      {action}
    </div>
  );
}
