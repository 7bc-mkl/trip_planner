import i18n from 'i18next'
import ICU from 'i18next-icu'
import { initReactI18next } from 'react-i18next'

import en from '../locales/en.json'
import pl from '../locales/pl.json'

/**
 * i18next with ICU message formatting (spec A6).
 *
 * ICU is what keeps `scripts/check_locales.py` green without editing the gate.
 * i18next's *default* pluralisation appends a CLDR category to the key, so a
 * counted noun ships as `key_one`/`key_other` in English and
 * `key_one`/`key_few`/`key_many`/`key_other` in Polish — four keys against two,
 * which the gate reports as extra keys in `pl`. ICU moves the plural selection
 * inside a single key's value, so both files keep identical key sets.
 */

export const SUPPORTED_LOCALES = ['pl', 'en'] as const
export type Locale = (typeof SUPPORTED_LOCALES)[number]

export const DEFAULT_LOCALE: Locale = 'pl'
const STORAGE_KEY = 'trip-planner.locale'

export function isLocale(value: unknown): value is Locale {
  return typeof value === 'string' && (SUPPORTED_LOCALES as readonly string[]).includes(value)
}

/** The locale to start in: an explicit earlier choice, then the browser, then the default. */
export function detectInitialLocale(): Locale {
  if (typeof window !== 'undefined') {
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY)
      if (isLocale(stored)) {
        return stored
      }
    } catch {
      // A browser with storage disabled still gets a working app, just no memory.
    }

    const fromNavigator = window.navigator?.language?.split('-')[0]
    if (isLocale(fromNavigator)) {
      return fromNavigator
    }
  }

  return DEFAULT_LOCALE
}

/**
 * Apply a locale everywhere it is observable: i18next, `<html lang>` (R01) and
 * the persisted preference. The owner's server-side `locale` is the source of
 * truth once signed in; this keeps the signed-out screen consistent with it.
 */
export function applyLocale(locale: Locale): Promise<unknown> {
  if (typeof document !== 'undefined') {
    document.documentElement.setAttribute('lang', locale)
  }

  if (typeof window !== 'undefined') {
    try {
      window.localStorage.setItem(STORAGE_KEY, locale)
    } catch {
      // Persistence is a convenience; failing to store it must not break the switch.
    }
  }

  return i18n.changeLanguage(locale)
}

export function initI18n(locale: Locale = detectInitialLocale()) {
  if (!i18n.isInitialized) {
    void i18n
      .use(ICU)
      .use(initReactI18next)
      .init({
        resources: {
          en: { translation: en },
          pl: { translation: pl },
        },
        lng: locale,
        fallbackLng: 'en',
        supportedLngs: SUPPORTED_LOCALES,
        interpolation: { escapeValue: false },
        returnNull: false,
      })
  }

  if (typeof document !== 'undefined') {
    document.documentElement.setAttribute('lang', locale)
  }

  return i18n
}

export default i18n
