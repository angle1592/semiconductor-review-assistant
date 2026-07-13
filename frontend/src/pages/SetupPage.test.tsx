import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AppRoutes } from '../App'


describe('first-run setup', () => {
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('defaults to OpenAI-compatible configuration and keeps Codex advanced', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter initialEntries={['/setup']}>
        <AppRoutes />
      </MemoryRouter>,
    )

    expect(screen.getByRole('heading', { name: '先连接你的 AI 服务' })).toBeInTheDocument()
    expect(screen.getByLabelText('服务地址')).toHaveValue('https://api.openai.com/v1')
    expect(screen.queryByText('使用本机 Codex 登录')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '高级：使用 Codex' }))
    expect(screen.getByText('使用本机 Codex 登录')).toBeInTheDocument()
  })

  it('saves the user key without echoing it back', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        provider: 'openai_compatible',
        base_url: 'https://models.example/v1',
        model: 'fast-model',
        api_key_configured: true,
        vision_enabled: true,
      }),
    })
    vi.stubGlobal('fetch', fetchMock)

    render(
      <MemoryRouter initialEntries={['/setup']}>
        <AppRoutes />
      </MemoryRouter>,
    )

    await user.clear(screen.getByLabelText('服务地址'))
    await user.type(screen.getByLabelText('服务地址'), 'https://models.example/v1')
    await user.type(screen.getByLabelText('模型名称'), 'fast-model')
    await user.type(screen.getByLabelText('API Key'), 'private-test-key')
    await user.click(screen.getByRole('button', { name: '保存并进入复习台' }))

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/settings/ai'),
      expect.objectContaining({ method: 'PUT' }),
    )
    expect(await screen.findByRole('heading', { name: '今天，先把课堂留下来' })).toBeInTheDocument()
    expect(screen.queryByDisplayValue('private-test-key')).not.toBeInTheDocument()
  })
})
