import { useTranslation } from 'react-i18next'

import { LocaleSwitch } from './i18n/LocaleSwitch'

export default function App() {
  const { t } = useTranslation()

  return (
    <div className="app">
      <header>
        <h1>{t('app.name')}</h1>
        <LocaleSwitch />
      </header>
    </div>
  )
}
