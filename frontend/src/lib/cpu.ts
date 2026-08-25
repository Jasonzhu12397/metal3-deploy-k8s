// Client-side mirror of backend/app/services/cpu_topology.py so the pool
// assignment screen can show a live "reserved cpus" / core-map preview as
// the operator drags the reserved-cores-per-socket slider, without a
// round-trip per keystroke. Must stay numerically identical to the Python
// version -- see backend/tests/test_asset_planner.py for the reference case.

export function computeReservedCpus(
  sockets: number,
  coresPerSocket: number,
  reservedPerSocket: number,
  threadsPerCore = 2,
): number[] {
  const totalPhysical = sockets * coresPerSocket;
  const reserved: number[] = [];
  for (let socket = 0; socket < sockets; socket++) {
    const base = socket * coresPerSocket;
    for (let i = 0; i < reservedPerSocket; i++) {
      const physicalCore = base + i;
      reserved.push(physicalCore);
      for (let t = 1; t < threadsPerCore; t++) {
        reserved.push(physicalCore + totalPhysical * t);
      }
    }
  }
  return reserved;
}

export function totalLogicalCpus(sockets: number, coresPerSocket: number, threadsPerCore: number): number {
  return sockets * coresPerSocket * threadsPerCore;
}

export function isolatedCpuCount(
  sockets: number,
  coresPerSocket: number,
  threadsPerCore: number,
  reservedPerSocket: number,
): number {
  return (
    totalLogicalCpus(sockets, coresPerSocket, threadsPerCore) -
    sockets * reservedPerSocket * threadsPerCore
  );
}
