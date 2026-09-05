import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'

import { LocaleSwitch } from './LocaleSwitch'
import i18n, { applyLocale, detectInitialLocale, initI18n } from './index'
import en from '../locales/en.json'
import pl from '../locales/pl.json'

beforeEach(async () => {
  initI18n('pl')
  await applyLocale('pl')
})

/**
 * The proving string for the ICU decision (spec A6). Polish resolves counted
 * nouns to four CLDR categories against English's two, so a library that
 * pluralises by key suffix would put keys in `pl.json` that `en.json` does not
 * define — exactly what `scripts/check_locales.py` fails on. These assertions
 * fail if the ICU formatter is ever dropped.
 */
describe('Polish ICU pluralisation', () => {
  it.each([
    [1, '1 etap'],
    [2, '2 etapy'],
    [3, '3 etapy'],
    [4, '4 etapy'],
    [5, '5 etapów'],
    [11, '11 etapów'],
    [22, '22 etapy'],
  ])('renders the stage count for %i as "%s"', (count, expected) => {
    expect(i18n.t('trip.stageCount', { count })).toBe(expected)
  })

  it.each([
    [1, '1 noc'],
    [2, '2 noce'],
    [5, '5 nocy'],
  ])('renders the night count for %i as "%s"', (count, expected) => {
    expect(i18n.t('trip.nightCount', { count })).toBe(expected)
  })

  it('renders the English forms from the same key', async () => {
    await applyLocale('en')
    expect(i18n.t('trip.stageCount', { count: 1 })).toBe('1 stage')
    expect(i18n.t('trip.stageCount', { count: 5 })).toBe('5 stages')
  })
})

describe('locale files', () => {
  const flatten = (value: unknown, prefix = ''): string[] => {
    if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
      return Object.entries(value).flatMap(([key, child]) =>
        flatten(child, prefix ? `${prefix}.${key}` : key),
      )
    }
    return [prefix]
  }

  it('define exactly the same keys — the parity the gate enforces', () => {
    expect(flatten(pl).sort()).toEqual(flatten(en).sort())
  })

  it('leave no value empty in either locale', () => {
    const values = (source: unknown): string[] => {
      if (source !== null && typeof source === 'object' && !Array.isArray(source)) {
        return Object.values(source).flatMap(values)
      }
      return [String(source)]
    }
    expect(values(en).filter((value) => value.trim() === '')).toEqual([])
    expect(values(pl).filter((value) => value.trim() === '')).toEqual([])
  })
})

describe('LocaleSwitch', () => {
  it('changes the language and the <html lang> attribute', async () => {
    const user = userEvent.setup()
    render(<LocaleSwitch />)

    expect(document.documentElement.getAttribute('lang')).toBe('pl')

    await user.selectOptions(screen.getByLabelText('Język'), 'en')

    expect(i18n.resolvedLanguage).toBe('en')
    expect(document.documentElement.getAttribute('lang')).toBe('en')
  })
})

describe('detectInitialLocale', () => {
  it('prefers a stored choice over the browser language', () => {
    window.localStorage.setItem('trip-planner.locale', 'en')
    expect(detectInitialLocale()).toBe('en')
    window.localStorage.removeItem('trip-planner.locale')
  })

  it('falls back to a supported locale when nothing is stored', () => {
    window.localStorage.removeItem('trip-planner.locale')
    expect(['pl', 'en']).toContain(detectInitialLocale())
  })
})
