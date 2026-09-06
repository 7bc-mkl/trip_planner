import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'

import App from './App'
import { SessionProvider } from './features/auth/SessionContext'
import { initI18n } from './i18n'
// Self-hosted Plus Jakarta Sans (Q2): the variable package's single `wght.css` axis file already
// bundles the `latin-ext` subset alongside `latin` (each gated by its own `unicode-range`), so one
// import covers the full 200-800 weight axis and the `ą ć ę ł ń ó ś ź ż` diacritics without a
// separate `latin-ext.css` — the package does not publish one for the variable build.
import '@fontsource-variable/plus-jakarta-sans/wght.css'
import './index.css'

initI18n()

const container = document.getElementById('root')
if (!container) {
  throw new Error('Root container #root is missing from index.html')
}

createRoot(container).render(
  <StrictMode>
    <BrowserRouter>
      <SessionProvider>
        <App />
      </SessionProvider>
    </BrowserRouter>
  </StrictMode>,
)
