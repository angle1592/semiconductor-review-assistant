import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'

import { AppRoutes } from '../App'


afterEach(() => vi.unstubAllGlobals())

it('lists multiple third-party services and their validation state', async () => {
  const provider = { id: 'p1', name: '主力服务', protocol: 'anthropic', base_url: 'https://relay.test/v1', enabled: true, is_default: true, credential_generation: 1, api_key_configured: true, models_fetched_at: null, created_at: '2026-07-16T12:00:00Z', updated_at: '2026-07-16T12:00:00Z' }
  const model = { id: 'm1', provider_id: 'p1', model_id: 'claude-test', display_name: 'Claude Test', text_status: 'passed', structured_status: 'passed', vision_status: 'passed', prompt_cache_status: 'passed', safe_error_code: null, validated_at: '2026-07-16T12:00:00Z' }
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url.endsWith('/api/providers')) return { ok: true, status: 200, json: async () => [provider] }
    if (url.endsWith('/api/providers/p1/models')) return { ok: true, status: 200, json: async () => [model] }
    if (url.endsWith('/api/system/info')) return { ok: true, status: 200, json: async () => ({ application: 'shiyao-review', version: '0.2.1-beta', packaged: false, setup_complete: true, data_directory: 'data', log_directory: 'logs' }) }
    if (url.endsWith('/api/system/caches')) return { ok: true, status: 200, json: async () => ({ parse: { files: 2, bytes: 2048 }, ai: { files: 1, bytes: 512 } }) }
    throw new Error(`Unexpected request: ${url}`)
  }))

  render(<MemoryRouter initialEntries={['/settings']}><AppRoutes /></MemoryRouter>)
  expect(await screen.findByRole('heading', { name: '设置' })).toBeInTheDocument()
  expect(await screen.findByRole('heading', { name: '主力服务' })).toBeInTheDocument()
  expect(screen.getByText('视觉：通过')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '新增服务' })).toBeInTheDocument()
})


it('shows cache impact and sends exact byte confirmation before clearing', async () => {
  const user = userEvent.setup()
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
  const calls: { url: string; init?: RequestInit }[] = []
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    calls.push({ url, init })
    if (url.endsWith('/api/providers')) return { ok: true, status: 200, json: async () => [] }
    if (url.endsWith('/api/system/info')) return { ok: true, status: 200, json: async () => ({ application: 'shiyao-review', version: '0.2.1-beta', packaged: false, setup_complete: true, data_directory: 'data', log_directory: 'logs' }) }
    if (url.endsWith('/api/system/caches') && !init?.method) return { ok: true, status: 200, json: async () => ({ parse: { files: 2, bytes: 2048 }, ai: { files: 1, bytes: 512 } }) }
    if (url.endsWith('/api/system/caches/parse/clear')) return { ok: true, status: 200, json: async () => ({ cleared: true, removed: { files: 2, bytes: 2048 }, current: { parse: { files: 0, bytes: 0 }, ai: { files: 1, bytes: 512 } } }) }
    throw new Error(`Unexpected request: ${url}`)
  }))

  render(<MemoryRouter initialEntries={['/settings']}><AppRoutes /></MemoryRouter>)
  await user.click(await screen.findByRole('button', { name: '清理解析缓存' }))

  expect(confirm).toHaveBeenCalledWith(expect.stringContaining('2048 字节'))
  expect(confirm).toHaveBeenCalledWith(expect.stringContaining('不会删除资料、重点、题目、复习内容或掌握记录'))
  const request = calls.find((call) => call.url.endsWith('/api/system/caches/parse/clear'))
  expect(JSON.parse(String(request?.init?.body))).toEqual({ expected_bytes: 2048, confirmation: 'CLEAR 2048' })
  expect(await screen.findByText('解析缓存已清理。')).toBeInTheDocument()
})
