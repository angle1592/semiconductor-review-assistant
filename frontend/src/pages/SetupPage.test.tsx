import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'

import { AppRoutes } from '../App'


afterEach(() => vi.unstubAllGlobals())

it('finishes setup only after a provider model is probed and enabled', async () => {
  const user = userEvent.setup()
  const provider = { id: 'p1', name: '主力服务', protocol: 'openai_compatible', base_url: 'https://relay.test/v1', enabled: false, is_default: false, credential_generation: 1, api_key_configured: true, models_fetched_at: null, created_at: '2026-07-16T12:00:00Z', updated_at: '2026-07-16T12:00:00Z' }
  const model = { id: 'm1', provider_id: 'p1', model_id: 'review-model', display_name: 'Review Model', text_status: 'untested', structured_status: 'untested', vision_status: 'untested', prompt_cache_status: 'unsupported', safe_error_code: null, validated_at: null }
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.endsWith('/api/providers') && init?.method === 'POST') return { ok: true, status: 201, json: async () => provider }
    if (url.endsWith('/api/providers/p1/models:refresh')) return { ok: true, status: 200, json: async () => [model] }
    if (url.endsWith('/api/providers/p1/models/m1:probe')) return { ok: true, status: 200, json: async () => ({ ...model, text_status: 'passed', structured_status: 'passed', vision_status: 'passed' }) }
    if (url.endsWith('/api/providers/p1:enable')) return { ok: true, status: 200, json: async () => ({ ...provider, enabled: true, is_default: true }) }
    if (url.endsWith('/api/system/setup-complete')) return { ok: true, status: 204 }
    if (url.endsWith('/api/projects')) return { ok: true, status: 200, json: async () => [] }
    throw new Error(`Unexpected request: ${url}`)
  }))

  render(<MemoryRouter initialEntries={['/setup']}><AppRoutes /></MemoryRouter>)
  await user.clear(screen.getByLabelText('API 地址'))
  await user.type(screen.getByLabelText('API 地址'), 'https://relay.test')
  await user.type(screen.getByLabelText('API Key'), 'private-test-key')
  await user.click(screen.getByRole('button', { name: '获取模型' }))
  await user.selectOptions(await screen.findByLabelText('模型'), 'm1')
  await user.click(screen.getByRole('button', { name: '校验模型能力' }))
  expect(await screen.findByText('视觉：通过')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: '启用此服务' }))
  expect(await screen.findByRole('heading', { name: '复习项目' })).toBeInTheDocument()
  expect(screen.queryByDisplayValue('private-test-key')).not.toBeInTheDocument()
})
