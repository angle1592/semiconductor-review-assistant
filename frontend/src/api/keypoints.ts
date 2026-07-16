import { request } from './client'

export type Importance = 'core' | 'important' | 'supplementary'
export type Candidate = {
  id: number; project_id: string; run_id: number; batch_id: number; title: string; explanation: string
  importance: Importance; source_block_ids: string[]; evidence_quotes: string[]; rationale: string
  status: 'pending' | 'confirmed' | 'rejected'; user_edited: boolean; confirmed_keypoint_id: number | null
  created_at: string; updated_at: string
}
export type KeyPoint = {
  id: number; project_id: string; title: string; explanation: string; importance: Importance
  source_block_ids: string[]; evidence_quotes: string[]; origin: 'manual' | 'ai'; run_id: number | null
  user_edited: boolean; position: number; created_at: string; updated_at: string
}
export type KeyPointInput = Pick<KeyPoint, 'title' | 'explanation' | 'importance' | 'source_block_ids' | 'evidence_quotes'>

export const keyPointKeys = {
  candidates: (runId: number) => ['keypoint-candidates', runId] as const,
  confirmed: (projectId: string) => ['keypoints', projectId] as const,
}

export const keypointsApi = {
  candidates: (runId: number) => request<Candidate[]>(`/api/analysis-runs/${runId}/candidates`),
  updateCandidate: (candidateId: number, payload: Partial<Pick<Candidate, 'title' | 'explanation' | 'importance' | 'rationale'>>) => request<Candidate>(`/api/keypoint-candidates/${candidateId}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  bulkAction: (confirmIds: number[], rejectIds: number[]) => request<{ confirmed: number; rejected: number; keypoint_ids: number[] }>('/api/keypoint-candidates:bulk-action', { method: 'POST', body: JSON.stringify({ confirm_ids: confirmIds, reject_ids: rejectIds }) }),
  list: (projectId: string) => request<KeyPoint[]>(`/api/projects/${projectId}/keypoints`),
  create: (projectId: string, payload: KeyPointInput) => request<KeyPoint>(`/api/projects/${projectId}/keypoints`, { method: 'POST', body: JSON.stringify(payload) }),
  update: (keyPointId: number, payload: Partial<KeyPointInput>) => request<KeyPoint>(`/api/keypoints/${keyPointId}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  remove: (keyPointId: number) => request<void>(`/api/keypoints/${keyPointId}`, { method: 'DELETE' }),
  reorder: (projectId: string, orderedIds: number[]) => request<KeyPoint[]>(`/api/projects/${projectId}/keypoints:reorder`, { method: 'POST', body: JSON.stringify({ ordered_ids: orderedIds }) }),
}
