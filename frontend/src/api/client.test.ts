import { afterEach, describe, expect, it, vi } from 'vitest'

import { api } from './client'


describe('project API client', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('creates a review project with the approved fields', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({
        id: 'project-1',
        name: '期末总复习',
        description: '综合资料',
        importance_prompt: '优先公式',
        created_at: '2026-07-16T12:00:00Z',
        updated_at: '2026-07-16T12:00:00Z',
      }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await api.createProject({
      name: '期末总复习',
      description: '综合资料',
      importance_prompt: '优先公式',
    })

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/projects'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          name: '期末总复习',
          description: '综合资料',
          importance_prompt: '优先公式',
        }),
      }),
    )
  })

  it('keeps the typed API code for actionable errors', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ code: 'NOT_FOUND', message: '项目不存在', action: 'open_project_index', context: { project_id: 'missing' } }),
    }))

    await expect(api.getProject('missing')).rejects.toMatchObject({
      status: 404,
      code: 'NOT_FOUND',
      message: '项目不存在',
      action: 'open_project_index',
      context: { project_id: 'missing' },
    })
  })
})
