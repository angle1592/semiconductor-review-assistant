import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'

import { AppRoutes } from '../App'


afterEach(() => vi.unstubAllGlobals())

it('shows only third-party API configuration', async () => {
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url.endsWith('/api/settings/ai')) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          provider: 'openai_compatible',
          base_url: 'https://api.example/v1',
          model: 'review-model',
          api_key_configured: true,
          vision_enabled: true,
        }),
      }
    }
    if (url.endsWith('/api/system/info')) {
      return { ok: true, status: 200, json: async () => ({ application: 'shiyao-review', version: '0.1.0', packaged: false, setup_complete: true, data_directory: 'data', log_directory: 'logs' }) }
    }
    throw new Error(`Unexpected request: ${url}`)
  }))

  render(
    <MemoryRouter initialEntries={['/settings']}>
      <AppRoutes />
    </MemoryRouter>,
  )

  expect(await screen.findByRole('heading', { name: '设置' })).toBeInTheDocument()
  expect(screen.getByText('OpenAI 兼容 API')).toBeInTheDocument()
})
