import { describe, it, expect } from 'vitest'
import { computeReservedCpus, totalLogicalCpus, isolatedCpuCount } from '../cpu'

// This file exists specifically to keep the promise in cpu.ts's own
// header comment: "Must stay numerically identical to the Python
// version". The reference values below are copied directly from
// backend/tests/test_asset_planner.py -- if someone changes the math on
// one side without the other, this is what catches it (previously:
// nothing did, on the frontend side).

describe('computeReservedCpus', () => {
  it('matches the Python reference case exactly (2 sockets x 32 cores, reserve 4/socket, SMT=2)', () => {
    // Python: compute_reserved_cpus(sockets=2, cores_per_socket=32, reserved_per_socket=4, threads_per_core=2)
    //   == "0,64,1,65,2,66,3,67,32,96,33,97,34,98,35,99"
    // (a comma-joined string there vs. an array here -- joining this
    // array with ',' must produce that exact string)
    const result = computeReservedCpus(2, 32, 4, 2)
    expect(result.join(',')).toBe('0,64,1,65,2,66,3,67,32,96,33,97,34,98,35,99')
  })

  it('reserves nothing when reservedPerSocket is 0', () => {
    expect(computeReservedCpus(2, 32, 0, 2)).toEqual([])
  })

  it('handles no-hyperthreading (threadsPerCore=1) by reserving only physical cores, no sibling', () => {
    const result = computeReservedCpus(2, 32, 4, 1)
    // no SMT sibling threads to add -- just the 4 physical cores per socket
    expect(result).toEqual([0, 1, 2, 3, 32, 33, 34, 35])
  })

  it('handles a single socket', () => {
    const result = computeReservedCpus(1, 16, 2, 2)
    // totalPhysical=16, socket 0 only: cores 0,1 + their SMT siblings at +16
    expect(result).toEqual([0, 16, 1, 17])
  })
})

describe('totalLogicalCpus', () => {
  it('matches the Python reference case (2x32x2 = 128 logical)', () => {
    expect(totalLogicalCpus(2, 32, 2)).toBe(128)
  })

  it('is just sockets * cores * threads with no SMT', () => {
    expect(totalLogicalCpus(2, 32, 1)).toBe(64)
  })
})

describe('isolatedCpuCount', () => {
  it('matches the Python reference case exactly (128 logical - 16 reserved = 112)', () => {
    // Python: isolated_cpu_count(sockets=2, cores_per_socket=32, threads_per_core=2, reserved_per_socket=4) == 112
    expect(isolatedCpuCount(2, 32, 2, 4)).toBe(112)
  })

  it('equals total logical CPUs when nothing is reserved', () => {
    expect(isolatedCpuCount(2, 32, 2, 0)).toBe(totalLogicalCpus(2, 32, 2))
  })

  it('never goes negative for a sane reservation (reserved cores stay within the physical core count)', () => {
    // reserving every physical core on every socket -- isolated count
    // should bottom out at 0, not go negative
    const result = isolatedCpuCount(2, 32, 2, 32)
    expect(result).toBe(0)
  })
})
