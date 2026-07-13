import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AppRoutes } from '../App'


describe('desktop settings controls', () => {
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('opens only the requested local directory', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/api/settings/ai')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            provider: 'openai_compatible',
            base_url: 'https://api.openai.com/v1',
            model: 'gpt-4.1-mini',
            api_key_configured: false,
            vision_enabled: true,
          }),
        }
      }
      if (url.endsWith('/api/system/paths/logs/open')) return { ok: true, status: 204 }
      throw new Error(`Unexpected request: ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    render(
      <MemoryRouter initialEntries={['/settings']}>
        <AppRoutes />
      </MemoryRouter>,
    )

    await user.click(await screen.findByRole('button', { name: '打开日志目录' }))
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/system/paths/logs/open'),
      expect.objectContaining({ method: 'POST' }),
    )
    expect(screen.getByRole('button', { name: '导出诊断包' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '退出本地服务' })).toBeInTheDocument()
  })
})
