import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { LanguageProvider, useLanguage } from '../index'

// The compile-time zh/en key-parity check (translations.ts's
// _AssertParity types) already guards that both languages define the
// same keys -- that's a real, valuable check, but it's a TypeScript-only
// guarantee. It says nothing about whether the *runtime* behavior
// (localStorage persistence, browser-locale detection, toggling,
// {var} interpolation) actually works. That's what these tests cover.

const STORAGE_KEY = 'metal3_console_language'

function Probe() {
  const { language, t, toggleLang, setLanguage } = useLanguage()
  return (
    <div>
      <span data-testid="lang">{language}</span>
      <span data-testid="translated">{t('nav.overview')}</span>
      <button onClick={toggleLang}>toggle</button>
      <button onClick={() => setLanguage('en')}>force-en</button>
    </div>
  )
}

beforeEach(() => {
  localStorage.clear()
})

describe('LanguageProvider / useLanguage', () => {
  it('throws a clear error when used outside a LanguageProvider', () => {
    // Suppress React's expected console.error for this render-time throw
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(() => render(<Probe />)).toThrow('useLanguage must be used inside <LanguageProvider>')
    spy.mockRestore()
  })

  it('falls back to the browser locale on first visit when nothing is stored', () => {
    vi.spyOn(window.navigator, 'language', 'get').mockReturnValue('zh-CN')
    render(
      <LanguageProvider>
        <Probe />
      </LanguageProvider>,
    )
    expect(screen.getByTestId('lang').textContent).toBe('zh')
    expect(screen.getByTestId('translated').textContent).toBe('概览')
  })

  it('falls back to English when the browser locale is not Chinese', () => {
    vi.spyOn(window.navigator, 'language', 'get').mockReturnValue('en-US')
    render(
      <LanguageProvider>
        <Probe />
      </LanguageProvider>,
    )
    expect(screen.getByTestId('lang').textContent).toBe('en')
    expect(screen.getByTestId('translated').textContent).toBe('Overview')
  })

  it('reads a previously-stored language preference instead of the browser locale', () => {
    localStorage.setItem(STORAGE_KEY, 'en')
    vi.spyOn(window.navigator, 'language', 'get').mockReturnValue('zh-CN') // would say zh if this were ignored
    render(
      <LanguageProvider>
        <Probe />
      </LanguageProvider>,
    )
    expect(screen.getByTestId('lang').textContent).toBe('en')
  })

  it('toggleLang flips the language and persists the choice to localStorage', () => {
    localStorage.setItem(STORAGE_KEY, 'zh')
    render(
      <LanguageProvider>
        <Probe />
      </LanguageProvider>,
    )
    expect(screen.getByTestId('lang').textContent).toBe('zh')

    fireEvent.click(screen.getByText('toggle'))

    expect(screen.getByTestId('lang').textContent).toBe('en')
    expect(screen.getByTestId('translated').textContent).toBe('Overview')
    expect(localStorage.getItem(STORAGE_KEY)).toBe('en')
  })

  it('setLanguage sets an explicit language regardless of the current one', () => {
    localStorage.setItem(STORAGE_KEY, 'zh')
    render(
      <LanguageProvider>
        <Probe />
      </LanguageProvider>,
    )
    fireEvent.click(screen.getByText('force-en'))
    expect(screen.getByTestId('lang').textContent).toBe('en')
    expect(localStorage.getItem(STORAGE_KEY)).toBe('en')
  })

  it('interpolates {var} placeholders with the provided values', () => {
    localStorage.setItem(STORAGE_KEY, 'zh')
    function InterpolationProbe() {
      const { t } = useLanguage()
      return <span data-testid="out">{t('catalog.resultsCount', { count: 7 })}</span>
    }
    render(
      <LanguageProvider>
        <InterpolationProbe />
      </LanguageProvider>,
    )
    expect(screen.getByTestId('out').textContent).toBe('共 7 个组件')
  })

  it('falls back to the zh translation if a key were ever missing from the current language (defensive runtime behavior)', () => {
    // Can't easily construct a genuinely-missing key since translations.ts's
    // types forbid it at compile time -- this exercises the same code
    // path (dict[key] ?? translations.zh[key] ?? key) with a
    // runtime-only invalid key to confirm the fallback chain itself
    // works, which matters if the dictionaries ever drift via some
    // non-type-checked path (e.g. a key computed from a template string).
    localStorage.setItem(STORAGE_KEY, 'en')
    function FallbackProbe() {
      const { t } = useLanguage()
      // @ts-expect-error -- deliberately testing the runtime fallback for a key TypeScript would normally reject
      return <span data-testid="out">{t('this.key.does.not.exist')}</span>
    }
    render(
      <LanguageProvider>
        <FallbackProbe />
      </LanguageProvider>,
    )
    // falls all the way through to returning the key itself, not a crash
    expect(screen.getByTestId('out').textContent).toBe('this.key.does.not.exist')
  })
})
