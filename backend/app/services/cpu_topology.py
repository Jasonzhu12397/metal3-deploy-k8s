"""
Computes kubelet `reserved_cpus` (and matching hugepage/isolation config)
from an asset's CPU topology, instead of a human hand-typing strings like
"0,64,1,65,2,66,3,67,32,96,33,97,34,98,35,99".

Convention mirrored from the operator's existing config: physical cores
are laid out contiguously per socket (socket N occupies
[N*cores_per_socket, (N+1)*cores_per_socket)), and each physical core's
hyperthread sibling sits at `physical_core_id + total_physical_cores`.
Reserving `reserved_per_socket` cores of a socket reserves both the
physical core and its HT sibling for host/kubelet/system use, leaving
the rest for Guaranteed-QoS / DPDK workloads.
"""
from __future__ import annotations


def compute_reserved_cpus(
    sockets: int,
    cores_per_socket: int,
    reserved_per_socket: int,
    threads_per_core: int = 2,
) -> str:
    if reserved_per_socket > cores_per_socket:
        raise ValueError("reserved_per_socket cannot exceed cores_per_socket")

    total_physical = sockets * cores_per_socket
    reserved: list[int] = []

    for socket in range(sockets):
        base = socket * cores_per_socket
        for i in range(reserved_per_socket):
            physical_core = base + i
            reserved.append(physical_core)
            for t in range(1, threads_per_core):
                reserved.append(physical_core + total_physical * t)

    return ",".join(str(c) for c in reserved)


def total_logical_cpus(sockets: int, cores_per_socket: int, threads_per_core: int) -> int:
    return sockets * cores_per_socket * threads_per_core


def reserved_cpu_count(sockets: int, reserved_per_socket: int, threads_per_core: int) -> int:
    return sockets * reserved_per_socket * threads_per_core


def isolated_cpu_count(
    sockets: int, cores_per_socket: int, threads_per_core: int, reserved_per_socket: int
) -> int:
    return total_logical_cpus(sockets, cores_per_socket, threads_per_core) - reserved_cpu_count(
        sockets, reserved_per_socket, threads_per_core
    )
