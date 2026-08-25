import { computeReservedCpus, totalLogicalCpus } from "../../lib/cpu";

/**
 * The platform's signature visual: a literal map of every logical CPU on a
 * box, colored by what it's used for. This is not decoration -- it's the
 * same reserved-cpus computation the backend renders into
 * KubeadmConfigTemplate, just drawn instead of printed as a comma string,
 * so an operator can see at a glance what "reserve 4 cores/socket" costs
 * them before committing to it.
 */
export function CoreMap({
  sockets,
  coresPerSocket,
  threadsPerCore,
  reservedPerSocket,
  compact = false,
}: {
  sockets: number;
  coresPerSocket: number;
  threadsPerCore: number;
  reservedPerSocket: number;
  compact?: boolean;
}) {
  const total = totalLogicalCpus(sockets, coresPerSocket, threadsPerCore);
  const reservedSet = new Set(computeReservedCpus(sockets, coresPerSocket, reservedPerSocket, threadsPerCore));

  if (!total) {
    return <p className="text-xs text-[var(--color-ink-faint)]">暂无 CPU 拓扑数据</p>;
  }

  const cellSize = compact ? 6 : 9;
  const gap = compact ? 1.5 : 2;

  return (
    <div className="flex flex-col gap-2">
      {Array.from({ length: sockets }).map((_, socket) => {
        const start = socket * coresPerSocket * threadsPerCore;
        return (
          <div key={socket} className="flex items-center gap-2">
            {!compact && (
              <span className="w-14 shrink-0 text-[11px] font-semibold text-[var(--color-ink-faint)]">
                Socket {socket}
              </span>
            )}
            <div className="flex flex-wrap" style={{ gap }}>
              {Array.from({ length: coresPerSocket * threadsPerCore }).map((_, offset) => {
                const cpuId = start + offset;
                const reserved = reservedSet.has(cpuId);
                return (
                  <div
                    key={cpuId}
                    title={`cpu${cpuId}${reserved ? " · reserved" : " · isolated (workload)"}`}
                    style={{
                      width: cellSize,
                      height: cellSize,
                      background: reserved ? "var(--color-core-reserved)" : "var(--color-core-isolated)",
                      borderRadius: 1.5,
                    }}
                  />
                );
              })}
            </div>
          </div>
        );
      })}
      {!compact && (
        <div className="mt-1 flex items-center gap-4 text-[11px] text-[var(--color-ink-muted)]">
          <LegendDot color="var(--color-core-reserved)" label="系统预留" />
          <LegendDot color="var(--color-core-isolated)" label="业务隔离可用" />
          <span className="text-[var(--color-ink-faint)]">共 {total} 逻辑核</span>
        </div>
      )}
    </div>
  );
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="inline-block h-2 w-2 rounded-sm" style={{ background: color }} />
      {label}
    </span>
  );
}
