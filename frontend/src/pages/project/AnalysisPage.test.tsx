import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'

import type { ReviewProject } from '../../api/client'
import { AnalysisPage } from './AnalysisPage'


afterEach(() => vi.unstubAllGlobals())

it('shows range cost, explicit whole-source confirmation and queued progress', async () => {
  const user = userEvent.setup()
  const project: ReviewProject = { id: 'project-1', name: '期末总复习', description: '', importance_prompt: '优先公式与易错点', created_at: '2026-07-16T12:00:00Z', updated_at: '2026-07-16T12:00:00Z' }
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.endsWith('/api/providers')) return { ok: true, status: 200, json: async () => [{ id: 'p1', name: '主力服务', protocol: 'anthropic', base_url: 'https://provider.test/v1', enabled: true, is_default: true, credential_generation: 1, api_key_configured: true, models_fetched_at: null, created_at: '', updated_at: '' }] }
    if (url.endsWith('/api/providers/p1/models')) return { ok: true, status: 200, json: async () => [{ id: 'm1', provider_id: 'p1', model_id: 'review-model', display_name: 'Review Model', text_status: 'passed', structured_status: 'passed', vision_status: 'passed', prompt_cache_status: 'passed', safe_error_code: null, validated_at: '' }] }
    if (url.endsWith('/analysis-range:estimate')) return { ok: true, status: 200, json: async () => ({ source_count: 3, block_count: 620, page_count: 88, character_count: 42000, image_count: 8, exceeds_warning: true }) }
    if (url.endsWith('/analysis-runs') && init?.method === 'POST') return { ok: true, status: 202, json: async () => ({ run_id: 44, job_id: 81, status: 'queued', batch_count: 7, message: '已加入分析队列，可离开此页面；任务会在后台继续。' }) }
    if (url.endsWith('/api/analysis-runs/44')) return { ok: true, status: 200, json: async () => ({ id: 44, project_id: 'project-1', status: 'queued', total_batches: 7, completed_batches: 0, failed_batches: 0, cancellation_requested: false, public_error_code: null, error_detail: null, batches: [{ id: 1, ordinal: 0, status: 'queued', attempts: 0, cache_status: null, public_error_code: null, error_detail: null }] }) }
    throw new Error(`Unexpected request: ${url}`)
  }))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

  render(
    <QueryClientProvider client={client}>
      <AnalysisPage project={project} selectedBlockIds={['a']} activeRunId={null} onActiveRunIdChange={() => undefined} />
    </QueryClientProvider>,
  )

  expect(screen.getByText(/AI 结果必须由你确认/)).toBeInTheDocument()
  await user.click(screen.getByLabelText('分析项目内全部资料'))
  expect(await screen.findByText('88 页 · 620 个内容块')).toBeInTheDocument()
  expect(screen.getByText(/范围较大/)).toBeInTheDocument()
  const start = screen.getByRole('button', { name: '开始后台分析' })
  expect(start).toBeDisabled()
  await user.click(screen.getByLabelText(/我确认分析全部资料/))
  await user.click(start)

  expect(await screen.findByText(/已加入分析队列/)).toBeInTheDocument()
  expect(screen.getByText('等待 worker 接手')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '取消分析' })).toBeInTheDocument()
})

