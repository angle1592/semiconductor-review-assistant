import { request } from './client'

export type AnalysisScope = { mode: 'selected_blocks'; block_ids: string[] } | { mode: 'all_sources'; block_ids: [] }
export type AnalysisEstimate = {
  source_count: number
  block_count: number
  page_count: number
  character_count: number
  image_count: number
  exceeds_warning: boolean
}
export type AnalysisBatch = {
  id: number
  ordinal: number
  status: string
  attempts: number
  cache_status: string | null
  public_error_code: string | null
  error_detail: string | null
}
export type AnalysisRun = {
  id: number
  project_id: string
  status: 'queued' | 'running' | 'partial' | 'succeeded' | 'failed' | 'cancelled'
  total_batches: number
  completed_batches: number
  failed_batches: number
  cancellation_requested: boolean
  public_error_code: string | null
  error_detail: string | null
  batches: AnalysisBatch[]
}
export type CreateAnalysisRun = {
  scope: AnalysisScope
  provider_id: string
  model_profile_id: string
  run_override: string
  parameters: { temperature: number }
  confirm_large_range: boolean
}
export type AnalysisRunCreated = { run_id: number; job_id: number; status: string; batch_count: number; message: string }

export const analysisKeys = {
  estimate: (projectId: string, scope: AnalysisScope) => ['analysis-estimate', projectId, scope] as const,
  run: (runId: number) => ['analysis-run', runId] as const,
}

export const analysisApi = {
  estimate: (projectId: string, scope: AnalysisScope) => request<AnalysisEstimate>(`/api/projects/${projectId}/analysis-range:estimate`, { method: 'POST', body: JSON.stringify(scope) }),
  create: (projectId: string, payload: CreateAnalysisRun) => request<AnalysisRunCreated>(`/api/projects/${projectId}/analysis-runs`, { method: 'POST', body: JSON.stringify(payload) }),
  get: (runId: number) => request<AnalysisRun>(`/api/analysis-runs/${runId}`),
  cancel: (runId: number) => request<{ run_id: number; status: string; cancellation_requested: boolean }>(`/api/analysis-runs/${runId}/cancel`, { method: 'POST' }),
  retry: (runId: number) => request<{ run_id: number; job_id: number; status: string; retried_batch_ids: number[] }>(`/api/analysis-runs/${runId}/retry`, { method: 'POST' }),
}
