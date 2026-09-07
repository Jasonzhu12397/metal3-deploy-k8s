import clsx from "clsx";
import { useLanguage } from "../../lib/i18n";
import type { TranslationKey } from "../../lib/i18n/translations";

type Tone = "success" | "processing" | "warning" | "danger" | "idle";

const TONE_MAP: Record<string, Tone> = {
  // clusters
  ready: "success",
  bootstrapping: "processing",
  provisioning: "processing",
  pending: "idle",
  failed: "danger",
  deleting: "warning",
  // BMH
  available: "success",
  inspecting: "processing",
  registering: "processing",
  provisioned: "success",
  deprovisioning: "warning",
  error: "danger",
  unknown: "idle",
  // hardware assets
  discovered: "idle",
  reserved: "processing",
  decommissioned: "danger",
  // deployments
  queued: "idle",
  generating_manifests: "processing",
  bootstrapping_ephemeral_node: "processing",
  applying_bmh: "processing",
  waiting_for_hosts: "processing",
  applying_cluster: "processing",
  waiting_for_control_plane: "processing",
  installing_addons: "processing",
  pivoting_to_target_cluster: "processing",
  complete: "success",
  // AI workloads
  deploying: "processing",
  running: "success",
};

// Every key here must exactly match a status string in TONE_MAP above --
// see the "status.*" section of lib/i18n/translations.ts. Status strings
// that don't appear here (a future addition, or a value some other
// backend deployment invents) still render via the humanized-string
// fallback below rather than crashing, just untranslated.
//
// Cast to Record<string, TranslationKey> rather than the more "precise"
// `status.${string}` template literal type Object.fromEntries would
// otherwise infer: that template type is broader than the actual
// TranslationKey union (it matches ANY string after "status.", not just
// the ones translations.ts really defines), so `t()` -- which requires
// a genuine TranslationKey -- correctly refuses it. This assertion is
// only safe because every value constructed here is a literal
// `status.${the same string as TONE_MAP's own key}`, and this project's
// zh/en dictionaries are kept in lockstep (see translations.ts's own
// compile-time parity check) with one status.* entry per TONE_MAP key --
// verified by hand when TONE_MAP gained pivoting_to_target_cluster.
const STATUS_KEYS: Record<string, TranslationKey> = Object.fromEntries(
  Object.keys(TONE_MAP).map((status) => [status, `status.${status}` as TranslationKey]),
);

const TONE_STYLES: Record<Tone, string> = {
  success: "bg-[var(--color-success-soft)] text-[var(--color-success)]",
  processing: "bg-[var(--color-processing-soft)] text-[var(--color-processing)]",
  warning: "bg-[var(--color-warning-soft)] text-[var(--color-warning)]",
  danger: "bg-[var(--color-danger-soft)] text-[var(--color-danger)]",
  idle: "bg-[var(--color-idle-soft)] text-[var(--color-idle)]",
};

export function StatusTag({ status, label }: { status: string; label?: string }) {
  const { t } = useLanguage();
  const tone = TONE_MAP[status] ?? "idle";
  const isLive = tone === "processing";
  const statusKey = STATUS_KEYS[status];
  // Every known status has a translation; an unrecognized one (not in
  // TONE_MAP, so not in STATUS_KEYS either) falls back to the humanized
  // raw string exactly as before this fix -- untranslated is still
  // better than a runtime error over a status value nothing anticipated.
  const displayText = label ?? (statusKey ? t(statusKey) : status.replace(/_/g, " "));
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold",
        TONE_STYLES[tone],
      )}
    >
      <span
        className={clsx("h-1.5 w-1.5 rounded-full bg-current", isLive && "pulse-dot")}
      />
      {displayText}
    </span>
  );
}
