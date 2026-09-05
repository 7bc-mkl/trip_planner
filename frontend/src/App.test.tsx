import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import App from './App'
import { initI18n } from './i18n'

describe('App', () => {
  it('renders the product name', () => {
    initI18n('pl')
    render(<App />)
    expect(screen.getByRole('heading', { name: 'Smart Trip Planner' })).toBeInTheDocument()
  })
})
