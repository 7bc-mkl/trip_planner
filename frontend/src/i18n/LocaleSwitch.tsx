import { useTranslation } from 'react-i18next'

import { SUPPORTED_LOCALES, applyLocale, isLocale } from './index'

/**
 * The locale switch. Present on every screen including `/login`, because R01
 * makes both languages first-class and a sign-in form the owner cannot read is
 * not a first-class language.
 */
export function LocaleSwitch({ onChange }: { onChange?: (locale: string) => void }) {
  const { t, i18n } = useTranslation()

  return (
    <label className="locale-switch">
      <span>{t('locale.label')}</span>
      <select
        value={i18n.resolvedLanguage}
        onChange={(event) => {
          const next = event.target.value
          if (!isLocale(next)) {
            return
          }
          void applyLocale(next)
          onChange?.(next)
        }}
      >
        {SUPPORTED_LOCALES.map((locale) => (
          <option key={locale} value={locale}>
            {t(`locale.${locale}`)}
          </option>
        ))}
      </select>
    </label>
  )
}
