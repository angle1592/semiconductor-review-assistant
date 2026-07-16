import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'

import { ReviewContentPage } from './ReviewContentPage'

afterEach(() => {
  sessionStorage.clear()
  vi.unstubAllGlobals()
})

it('explains generation prerequisites and restores a running artifact', async () => {
  const user = userEvent.setup()
  sessionStorage.setItem('shiyao:project:project-1:artifact', '7')
  const requests: string[] = []
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
    const url = String(input)
    requests.push(url)
    if (url.endsWith('/api/projects/project-1/keypoints')) return response([{ id: 3, project_id: 'project-1', title: '带隙定义', explanation: '定义', importance: 'core', source_block_ids: [], evidence_quotes: [], created_at: '', updated_at: '' }])
    if (url.endsWith('/api/projects/project-1/source-questions')) return response([])
    if (url.endsWith('/api/projects/project-1/artifacts')) return response([])
    if (url.endsWith('/api/artifacts/7')) return response({ id: 7, project_id: 'project-1', kind: 'outline', status: 'running', payload: {}, keypoint_ids: [3], source_question_ids: [], cache_status: null, public_error_code: null, error_detail: null, created_at: '', updated_at: '' })
    if (url.endsWith('/api/providers')) return response([{ id: 'p1', name: '主力服务', enabled: true }])
    throw new Error(`Unexpected request: ${url}`)
  }))

  renderPage()

  expect(await screen.findByText('生成任务正在后台运行')).toBeInTheDocument()
  expect(requests.some((url) => url.endsWith('/api/artifacts/7'))).toBe(true)
  expect(screen.getByText('请至少选择一个已确认重点。')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '生成复习提纲' })).toBeDisabled()
  expect(screen.getByText(/不设置日程、连续天数或自动下一场/)).toBeInTheDocument()
  expect(screen.queryByLabelText(/日程设置|每日安排|连续学习/)).not.toBeInTheDocument()

  await user.click(screen.getByText('带隙定义'))
  expect(screen.getByText('请选择已启用服务和已校验模型。')).toBeInTheDocument()
})

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><ReviewContentPage projectId="project-1" /></QueryClientProvider>)
}

function response(value: unknown) {
  return { ok: true, status: 200, json: async () => value }
}
