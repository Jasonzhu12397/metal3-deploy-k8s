import { X } from "lucide-react";
import type { ReactNode } from "react";

export function Modal({
  title,
  onClose,
  children,
  width = 520,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  width?: number;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-[rgba(16,21,42,0.45)] py-10">
      <div className="card w-full mx-4" style={{ maxWidth: width }}>
        <div className="flex items-center justify-between border-b border-[var(--color-border)] px-5 py-3.5">
          <h3 className="text-sm font-semibold">{title}</h3>
          <button onClick={onClose} className="btn-ghost btn rounded-md !p-1.5" aria-label="关闭">
            <X size={16} />
          </button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}
