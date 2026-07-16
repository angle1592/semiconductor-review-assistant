import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'

import { ProviderEditor } from './ProviderEditor'


afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

it('previews endpoints, fetches models, probes capabilities, and enables a provider', async () => {
  const user = userEvent.setup()
  const provider = {
    id: 'p1', name: '主力服务', protocol: 'anthropic', base_url: 'https://relay.test/v1',
    enabled: false, is_default: false, credential_generation: 1, api_key_configured: true,
    models_fetched_at: null, created_at: '2026-07-16T12:00:00Z', updated_at: '2026-07-16T12:00:00Z',
  }
  const model = {
    id: 'm1', provider_id: 'p1', model_id: 'claude-test', display_name: 'Claude Test',
    text_status: 'untested', structured_status: 'untested', vision_status: 'untested',
    prompt_cache_status: 'untested', safe_error_code: null, validated_at: null,
  }
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.endsWith('/api/providers') && init?.method === 'POST') return { ok: true, status: 201, json: async () => provider }
    if (url.endsWith('/api/providers/p1/models:refresh')) return { ok: true, status: 200, json: async () => [model] }
    if (url.endsWith('/api/providers/p1/models/m1:probe')) return { ok: true, status: 200, json: async () => ({ ...model, text_status: 'passed', structured_status: 'passed', vision_status: 'passed', prompt_cache_status: 'passed' }) }
    if (url.endsWith('/api/providers/p1:enable')) return { ok: true, status: 200, json: async () => ({ ...provider, enabled: true, is_default: true }) }
    throw new Error(`Unexpected request: ${url}`)
  }))

  render(<ProviderEditor onEnabled={vi.fn()} />)
  await user.selectOptions(screen.getByLabelText('协议'), 'anthropic')
  await user.clear(screen.getByLabelText('API 地址'))
  await user.type(screen.getByLabelText('API 地址'), 'https://relay.test')
  expect(screen.getByText('https://relay.test/v1/models')).toBeInTheDocument()
  await user.type(screen.getByLabelText('API Key'), 'sk-test')
  await user.click(screen.getByRole('button', { name: '获取模型' }))
  await user.selectOptions(await screen.findByLabelText('模型'), 'm1')
  await user.click(screen.getByRole('button', { name: '校验模型能力' }))
  expect(await screen.findByText('视觉：通过')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: '启用此服务' }))
  expect(await screen.findByText('服务已启用')).toBeInTheDocument()
  expect(screen.queryByDisplayValue('sk-test')).not.toBeInTheDocument()
})

it('explains how to recover when the provider rejects the API key', async () => {
  const user = userEvent.setup()
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: false,
    status: 401,
    json: async () => ({ code: 'upstream_auth_failed', message: '第三方服务拒绝了当前密钥。' }),
  }))

  render(<ProviderEditor onEnabled={vi.fn()} />)
  await user.type(screen.getByLabelText('API Key'), 'invalid-key')
  await user.click(screen.getByRole('button', { name: '获取模型' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('第三方服务拒绝了当前密钥。')
  expect(screen.getByRole('alert')).toHaveTextContent('重新填写 API Key 后再试。')
})
