import { Check, Copy } from "lucide-react";
import { useState } from "react";

export function CodeBlock({ code, language = "yaml" }: { code: string; language?: string }) {
  const [copied, setCopied] = useState(false);

  const onCopy = async () => {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="relative overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-navy-950)]">
      <div className="flex items-center justify-between border-b border-white/10 px-3 py-1.5">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-white/40">{language}</span>
        <button
          onClick={onCopy}
          className="flex items-center gap-1 rounded px-2 py-1 text-[11px] text-white/60 hover:bg-white/10 hover:text-white"
        >
          {copied ? <Check size={12} /> : <Copy size={12} />}
          {copied ? "已复制" : "复制"}
        </button>
      </div>
      <pre className="mono max-h-[480px] overflow-auto p-3.5 text-[12px] leading-relaxed text-[#d6dcf0]">
        {code}
      </pre>
    </div>
  );
}
