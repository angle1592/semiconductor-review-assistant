import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'

import { MasteryPage } from './MasteryPage'

afterEach(() => vi.unstubAllGlobals())

it('shows count-only mastery and filters records without scheduling study', async () => {
  const user = userEvent.setup()
  const urls: string[] = []
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
    const url = String(input)
    urls.push(url)
    if (url.endsWith('/mastery/summary')) return response({ total: 3, by_level: { unrated: 0, learning: 1, familiar: 1, mastered: 1 }, by_type: { keypoint: 1, artifact: 2 } })
    if (url.includes('/mastery')) return response([{ id: 5, project_id: 'project-1', target_type: 'artifact', target_id: 8, level: 'familiar', last_attempt_at: '2026-07-16T12:00:00Z', updated_at: '' }])
    throw new Error(`Unexpected request: ${url}`)
  }))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><MasteryPage projectId="project-1" /></QueryClientProvider>)

  expect(await screen.findByText('只记录你明确给出的判断')).toBeInTheDocument()
  expect(screen.getByText(/不推算考试日、到期日或连续学习/)).toBeInTheDocument()
  expect(screen.queryByText(/今日任务|连续打卡|下次复习/)).not.toBeInTheDocument()
  await user.selectOptions(screen.getByLabelText('按掌握程度筛选'), 'familiar')
  await user.selectOptions(screen.getByLabelText('按内容类型筛选'), 'artifact')
  await waitFor(() => expect(urls.some((url) => url.includes('level=familiar') && url.includes('target_type=artifact'))).toBe(true))
})

function response(value: unknown) {
  return { ok: true, status: 200, json: async () => value }
}
