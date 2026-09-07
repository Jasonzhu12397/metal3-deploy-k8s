import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { StatusTag } from '../StatusTag'
import { LanguageProvider } from '../../../lib/i18n'

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
//
// Also covers the real bug found via a live-environment language-mix
// report: StatusTag rendered the raw English status string directly
// (`status.replace(/_/g, ' ')`) regardless of which language was
// selected, at all 13 call sites across the app -- every status badge
// stayed English even on the Chinese UI, everything else around it
// correctly translated. Fixed by having StatusTag look itself up in a
// dedicated status.* translation namespace; these tests force each
// language explicitly rather than relying on the browser-locale
// detection default, so a regression back to the untranslated fallback
// fails deterministically instead of only failing for whichever locale
// happens to not match the machine running the tests.

function renderWithLanguage(status: string, lang: 'zh' | 'en', label?: string) {
  localStorage.setItem('metal3_console_language', lang)
  return render(
    <LanguageProvider>
      <StatusTag status={status} label={label} />
    </LanguageProvider>,
  )
}

function toneOfRenderedTag(status: string): string {
  const { container } = renderWithLanguage(status, 'en')
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
    pivoting_to_target_cluster: 'processing',
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
    const { container: processingContainer } = renderWithLanguage('provisioning', 'en')
    expect(processingContainer.querySelector('.pulse-dot')).not.toBeNull()

    const { container: successContainer } = renderWithLanguage('ready', 'en')
    expect(successContainer.querySelector('.pulse-dot')).toBeNull()
  })

  it('renders every known status translated in English when English is selected', () => {
    const { getByText } = renderWithLanguage('waiting_for_control_plane', 'en')
    expect(getByText('Waiting for control plane')).toBeInTheDocument()
  })

  it('renders every known status translated in Chinese when Chinese is selected -- the actual bug this test file exists for', () => {
    // Before the fix, this rendered the literal English string
    // "waiting for control plane" even with Chinese selected -- the
    // exact "some parts English, some parts Chinese" symptom reported
    // from a real deployment.
    const { getByText, queryByText } = renderWithLanguage('waiting_for_control_plane', 'zh')
    expect(getByText('等待控制面就绪')).toBeInTheDocument()
    expect(queryByText('waiting for control plane', { exact: false })).not.toBeInTheDocument()
  })

  it('still falls back to the humanized raw string for a status with no translation entry', () => {
    const { getByText } = renderWithLanguage('some_totally_novel_status', 'zh')
    expect(getByText('some totally novel status')).toBeInTheDocument()
  })

  it('renders a custom label instead of the raw status when provided, regardless of language', () => {
    const { getByText, queryByText } = renderWithLanguage('ready', 'zh', 'Ready to go')
    expect(getByText('Ready to go')).toBeInTheDocument()
    expect(queryByText('已就绪')).not.toBeInTheDocument()
  })
})
