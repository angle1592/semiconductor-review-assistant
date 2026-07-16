import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'

import { KeyPointsPage } from './KeyPointsPage'


afterEach(() => vi.unstubAllGlobals())

it('keeps AI output pending until the user edits and confirms it', async () => {
  const user = userEvent.setup()
  let candidate = { id: 1, project_id: 'project-1', run_id: 44, batch_id: 1, title: '带隙定义', explanation: '价带顶与导带底之间的能量差。', importance: 'core', source_block_ids: ['block-a'], evidence_quotes: ['带隙是能量差'], rationale: '基础定义', status: 'pending', user_edited: false, confirmed_keypoint_id: null, created_at: '', updated_at: '' }
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.endsWith('/api/analysis-runs/44/candidates')) return { ok: true, status: 200, json: async () => [candidate] }
    if (url.endsWith('/api/projects/project-1/keypoints')) return { ok: true, status: 200, json: async () => [] }
    if (url.endsWith('/api/keypoint-candidates/1') && init?.method === 'PATCH') {
      candidate = { ...candidate, title: '带隙核心定义', user_edited: true }
      return { ok: true, status: 200, json: async () => candidate }
    }
    if (url.endsWith('/api/keypoint-candidates:bulk-action')) return { ok: true, status: 200, json: async () => ({ confirmed: 1, rejected: 0, keypoint_ids: [9] }) }
    throw new Error(`Unexpected request: ${url}`)
  }))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

  render(
    <QueryClientProvider client={client}>
      <KeyPointsPage projectId="project-1" activeRunId={44} onOpenSourceBlock={() => undefined} />
    </QueryClientProvider>,
  )

  expect(await screen.findByText('待确认')).toBeInTheDocument()
  expect(screen.getByText('不会自动进入正式复习内容')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: '编辑 带隙定义' }))
  const title = screen.getByLabelText('候选标题')
  await user.clear(title)
  await user.type(title, '带隙核心定义')
  await user.click(screen.getByRole('button', { name: '保存候选修改' }))

  expect(await screen.findByText('带隙核心定义')).toBeInTheDocument()
  await user.click(screen.getByLabelText('选择候选 带隙核心定义'))
  await user.click(screen.getByRole('button', { name: '确认所选' }))
  expect(await screen.findByText(/已确认 1 条/)).toBeInTheDocument()
})
