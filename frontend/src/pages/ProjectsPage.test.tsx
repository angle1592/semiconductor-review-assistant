import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'

import { AppRoutes } from '../App'


afterEach(() => vi.unstubAllGlobals())

it('creates a review project and opens its six-step workspace', async () => {
  const user = userEvent.setup()
  const project = {
    id: 'project-1',
    name: '期末总复习',
    description: '材料综合复习',
    importance_prompt: '优先公式与易错点',
    created_at: '2026-07-16T12:00:00Z',
    updated_at: '2026-07-16T12:00:00Z',
  }
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.endsWith('/api/projects') && init?.method === 'POST') {
      return { ok: true, status: 201, json: async () => project }
    }
    if (url.endsWith('/api/projects/project-1')) {
      return { ok: true, status: 200, json: async () => project }
    }
    if (url.endsWith('/api/projects')) {
      return { ok: true, status: 200, json: async () => [] }
    }
    throw new Error(`Unexpected request: ${url}`)
  }))

  render(
    <MemoryRouter initialEntries={['/projects']}>
      <AppRoutes />
    </MemoryRouter>,
  )

  await user.click(await screen.findByRole('button', { name: '新建复习项目' }))
  await user.type(screen.getByLabelText('项目名称'), '期末总复习')
  await user.type(screen.getByLabelText('项目说明'), '材料综合复习')
  await user.type(screen.getByLabelText('什么内容最重要'), '优先公式与易错点')
  await user.click(screen.getByRole('button', { name: '创建项目' }))

  expect(await screen.findByRole('heading', { name: '期末总复习' })).toBeInTheDocument()
  for (const tab of ['概览', '资料', '分析', '重点', '复习', '掌握情况']) {
    expect(screen.getByRole('tab', { name: tab })).toBeInTheDocument()
  }
})

it('turns an empty or failed project list into a clear next action', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))
  render(
    <MemoryRouter initialEntries={['/projects']}>
      <AppRoutes />
    </MemoryRouter>,
  )

  expect(await screen.findByText('项目暂时无法读取')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '重新加载' })).toBeInTheDocument()
})
