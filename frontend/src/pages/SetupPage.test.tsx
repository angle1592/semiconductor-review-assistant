import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'

import { AppRoutes } from '../App'


afterEach(() => vi.unstubAllGlobals())

it('validates and saves a third-party API without exposing the key', async () => {
  const user = userEvent.setup()
  const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.endsWith('/api/settings/ai/test')) {
      return { ok: true, status: 200, json: async () => ({ ok: true, message: '连接成功', capabilities: ['text'] }) }
    }
    if (url.endsWith('/api/settings/ai') && init?.method === 'PUT') {
      return { ok: true, status: 200, json: async () => ({ provider: 'openai_compatible', base_url: 'https://api.example/v1', model: 'review-model', api_key_configured: true }) }
    }
    if (url.endsWith('/api/system/setup-complete')) {
      return { ok: true, status: 204 }
    }
    if (url.endsWith('/api/projects')) {
      return { ok: true, status: 200, json: async () => [] }
    }
    throw new Error(`Unexpected request: ${url}`)
  })
  vi.stubGlobal('fetch', fetchMock)

  render(
    <MemoryRouter initialEntries={['/setup']}>
      <AppRoutes />
    </MemoryRouter>,
  )

  await user.clear(screen.getByLabelText('API 地址'))
  await user.type(screen.getByLabelText('API 地址'), 'https://api.example/v1')
  await user.type(screen.getByLabelText('模型名称'), 'review-model')
  await user.type(screen.getByLabelText('API Key'), 'private-test-key')
  await user.click(screen.getByRole('button', { name: '测试、保存并继续' }))

  expect(await screen.findByRole('heading', { name: '复习项目' })).toBeInTheDocument()
  expect(screen.queryByDisplayValue('private-test-key')).not.toBeInTheDocument()
})
