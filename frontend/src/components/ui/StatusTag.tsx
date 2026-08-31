import clsx from "clsx";

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
  complete: "success",
  // AI workloads
  deploying: "processing",
  running: "success",
};

const TONE_STYLES: Record<Tone, string> = {
  success: "bg-[var(--color-success-soft)] text-[var(--color-success)]",
  processing: "bg-[var(--color-processing-soft)] text-[var(--color-processing)]",
  warning: "bg-[var(--color-warning-soft)] text-[var(--color-warning)]",
  danger: "bg-[var(--color-danger-soft)] text-[var(--color-danger)]",
  idle: "bg-[var(--color-idle-soft)] text-[var(--color-idle)]",
};

export function StatusTag({ status, label }: { status: string; label?: string }) {
  const tone = TONE_MAP[status] ?? "idle";
  const isLive = tone === "processing";
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
      {label ?? status.replace(/_/g, " ")}
    </span>
  );
}
