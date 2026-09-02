import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { StatusTag } from '../StatusTag'

// StatusTag is used on nearly every page (clusters, hosts, hardware
// assets, deployments, AI workloads) with each domain's own status
// strings mapped to one of 5 visual tones. A status silently falling
// through to "idle" (the ?? fallback) instead of its intended tone is
// exactly the kind of thing that's easy to introduce when adding a new
// feature's status enum and easy to miss in review -- this test file
// pins every currently-known status to its intended tone via the
// rendered dot's className, so an accidental remap or a forgotten new
// status shows up as a failing assertion instead of a silently-wrong
// color in production.

function toneOfRenderedTag(status: string): string {
  const { container } = render(<StatusTag status={status} />)
  // Color classes live on the OUTER span (TONE_STYLES applied there);
  // the inner dot only ever has "bg-current" plus optionally
  // "pulse-dot" -- querying the dot itself for a color class always
  // fails, regardless of which status is being tested.
  const tag = container.firstElementChild as HTMLElement
  if (tag.className.includes('color-success')) return 'success'
  if (tag.className.includes('color-processing')) return 'processing'
  if (tag.className.includes('color-warning')) return 'warning'
  if (tag.className.includes('color-danger')) return 'danger'
  if (tag.className.includes('color-idle')) return 'idle'
  throw new Error(`Could not determine tone from className: ${tag.className}`)
}

describe('StatusTag', () => {
  const expectedTones: Record<string, string> = {
    // clusters
    ready: 'success',
    bootstrapping: 'processing',
    provisioning: 'processing',
    pending: 'idle',
    failed: 'danger',
    deleting: 'warning',
    // BMH
    available: 'success',
    inspecting: 'processing',
    registering: 'processing',
    provisioned: 'success',
    deprovisioning: 'warning',
    error: 'danger',
    unknown: 'idle',
    // hardware assets
    discovered: 'idle',
    reserved: 'processing',
    decommissioned: 'danger',
    // deployments
    queued: 'idle',
    generating_manifests: 'processing',
    bootstrapping_ephemeral_node: 'processing',
    applying_bmh: 'processing',
    waiting_for_hosts: 'processing',
    applying_cluster: 'processing',
    waiting_for_control_plane: 'processing',
    installing_addons: 'processing',
    complete: 'success',
    // AI workloads
    deploying: 'processing',
    running: 'success',
  }

  for (const [status, tone] of Object.entries(expectedTones)) {
    it(`maps "${status}" to the "${tone}" tone`, () => {
      expect(toneOfRenderedTag(status)).toBe(tone)
    })
  }

  it('falls back to the idle tone for a genuinely unrecognized status rather than crashing', () => {
    expect(toneOfRenderedTag('some-status-nobody-defined')).toBe('idle')
  })

  it('shows the pulsing dot only for the processing tone', () => {
    const { container: processingContainer } = render(<StatusTag status="provisioning" />)
    expect(processingContainer.querySelector('.pulse-dot')).not.toBeNull()

    const { container: successContainer } = render(<StatusTag status="ready" />)
    expect(successContainer.querySelector('.pulse-dot')).toBeNull()
  })

  it('renders the status text with underscores replaced by spaces when no label is given', () => {
    const { getByText } = render(<StatusTag status="waiting_for_control_plane" />)
    expect(getByText('waiting for control plane')).toBeInTheDocument()
  })

  it('renders a custom label instead of the raw status when provided', () => {
    const { getByText, queryByText } = render(<StatusTag status="ready" label="Ready to go" />)
    expect(getByText('Ready to go')).toBeInTheDocument()
    expect(queryByText('ready')).not.toBeInTheDocument()
  })
})
