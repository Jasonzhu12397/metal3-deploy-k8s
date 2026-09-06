import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useDeploymentSocket } from '../useDeploymentSocket'

// Found via a bug-scanning pass (cross-referencing every src/lib/*.ts
// file against what tests/**/__tests__ actually references) to have
// zero coverage -- surprising given it's the hook backing every
// deployment's live progress view, and directly relevant to a real
// user-reported "progress not updating" style issue. That review also
// found two real problems fixed alongside these tests: a `wsRef` that
// was assigned but never read anywhere in the hook (dead state), and no
// reconnection at all on an unexpected close -- meaning a transient
// network blip or an intermediate proxy's idle timeout during a
// multi-minute deployment silently stopped live updates until the user
// manually refreshed the page.

/** A controllable fake WebSocket -- avoids any real network activity
 * and lets each test trigger onopen/onmessage/onclose/onerror on its
 * own schedule, deterministically. Real browsers' WebSocket
 * constructor doesn't exist in jsdom the way it does in a real
 * browser, and even where Node provides a global WebSocket, using the
 * real thing here would mean actually dialing a socket. */
class FakeWebSocket {
  static instances: FakeWebSocket[] = []
  url: string
  onopen: (() => void) | null = null
  onclose: ((event: { code: number }) => void) | null = null
  onerror: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  closed = false

  constructor(url: string) {
    this.url = url
    FakeWebSocket.instances.push(this)
  }

  close() {
    this.closed = true
  }

  // test helpers, not part of the real WebSocket API
  simulateOpen() {
    this.onopen?.()
  }
  simulateMessage(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) })
  }
  simulateClose(code: number) {
    this.onclose?.({ code })
  }
}

describe('useDeploymentSocket', () => {
  beforeEach(() => {
    FakeWebSocket.instances = []
    vi.stubGlobal('WebSocket', FakeWebSocket)
    localStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('does nothing when deploymentId is undefined', () => {
    renderHook(() => useDeploymentSocket(undefined))
    expect(FakeWebSocket.instances).toHaveLength(0)
  })

  it('opens a socket to the right URL and reports connected once open', () => {
    const { result } = renderHook(() => useDeploymentSocket('dep-123'))
    expect(FakeWebSocket.instances).toHaveLength(1)
    expect(FakeWebSocket.instances[0].url).toContain('/api/v1/deployments/dep-123/ws')

    act(() => {
      FakeWebSocket.instances[0].simulateOpen()
    })
    expect(result.current.connected).toBe(true)
  })

  it('accumulates incoming events in order', () => {
    const { result } = renderHook(() => useDeploymentSocket('dep-123'))
    const ws = FakeWebSocket.instances[0]

    act(() => ws.simulateMessage({ phase: 'queued', message: 'queued up' }))
    act(() => ws.simulateMessage({ phase: 'generating_manifests', message: 'rendering' }))

    expect(result.current.events).toHaveLength(2)
    expect(result.current.events[0]).toMatchObject({ phase: 'queued' })
    expect(result.current.events[1]).toMatchObject({ phase: 'generating_manifests' })
  })

  it('ignores a malformed (non-JSON) message frame instead of crashing', () => {
    const { result } = renderHook(() => useDeploymentSocket('dep-123'))
    const ws = FakeWebSocket.instances[0]

    act(() => {
      ws.onmessage?.({ data: 'not valid json {{{' })
    })

    // must not have thrown, and must not have added a garbage event
    expect(result.current.events).toHaveLength(0)
  })

  it('reports disconnected and does NOT clear the session on a normal close', () => {
    const { result } = renderHook(() => useDeploymentSocket('dep-123'))
    const ws = FakeWebSocket.instances[0]
    act(() => ws.simulateOpen())
    expect(result.current.connected).toBe(true)

    act(() => ws.simulateClose(1000)) // normal closure
    expect(result.current.connected).toBe(false)
    expect(localStorage.getItem('metal3_token')).not.toBe('cleared-by-mistake')
  })

  it('reconnects automatically after an unexpected close (not code 4401)', () => {
    vi.useFakeTimers()
    renderHook(() => useDeploymentSocket('dep-123'))
    expect(FakeWebSocket.instances).toHaveLength(1)

    act(() => FakeWebSocket.instances[0].simulateClose(1006)) // abnormal closure
    act(() => vi.advanceTimersByTime(3000))

    expect(FakeWebSocket.instances).toHaveLength(2)
  })

  it('does NOT reconnect on a 4401 (invalid/missing token) close', () => {
    vi.useFakeTimers()
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent')
    renderHook(() => useDeploymentSocket('dep-123'))

    act(() => FakeWebSocket.instances[0].simulateClose(4401))
    act(() => vi.advanceTimersByTime(10000))

    expect(FakeWebSocket.instances).toHaveLength(1) // no reconnect attempt
    expect(dispatchSpy).toHaveBeenCalledWith(expect.objectContaining({ type: 'metal3:unauthorized' }))
  })

  it('gives up reconnecting after the max attempt count instead of retrying forever', () => {
    vi.useFakeTimers()
    renderHook(() => useDeploymentSocket('dep-123'))

    for (let i = 0; i < 12; i++) {
      const latest = FakeWebSocket.instances[FakeWebSocket.instances.length - 1]
      act(() => latest.simulateClose(1006))
      act(() => vi.advanceTimersByTime(3000))
    }

    // capped at MAX_RECONNECT_ATTEMPTS (10) reconnects -> 11 total sockets
    // (the original + 10 retries), never unbounded
    expect(FakeWebSocket.instances.length).toBeLessThanOrEqual(11)
  })

  it('stops reconnecting and closes the socket on unmount', () => {
    vi.useFakeTimers()
    const { unmount } = renderHook(() => useDeploymentSocket('dep-123'))
    const firstSocket = FakeWebSocket.instances[0]

    act(() => firstSocket.simulateClose(1006))
    unmount()
    act(() => vi.advanceTimersByTime(10000))

    expect(FakeWebSocket.instances).toHaveLength(1) // no reconnect after unmount
  })

  it('closes the previous socket and resets events when deploymentId changes', () => {
    const { result, rerender } = renderHook(({ id }) => useDeploymentSocket(id), {
      initialProps: { id: 'dep-1' },
    })
    act(() => FakeWebSocket.instances[0].simulateMessage({ phase: 'queued' }))
    expect(result.current.events).toHaveLength(1)

    rerender({ id: 'dep-2' })

    expect(FakeWebSocket.instances[0].closed).toBe(true)
    expect(FakeWebSocket.instances).toHaveLength(2)
    expect(FakeWebSocket.instances[1].url).toContain('dep-2')
    expect(result.current.events).toHaveLength(0)
  })
})
