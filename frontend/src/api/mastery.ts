import { request } from './client'

export type MasteryLevel = 'unrated' | 'learning' | 'familiar' | 'mastered'
export type TargetType = 'keypoint' | 'source_question' | 'artifact'
export type MasteryRecord = { id: number; project_id: string; target_type: TargetType; target_id: number; level: MasteryLevel; last_attempt_at: string | null; updated_at: string }
export type MasterySummary = { total: number; by_level: Record<MasteryLevel, number>; by_type: Record<string, number> }
export const masteryKeys = { records: (projectId: string) => ['mastery', projectId] as const, summary: (projectId: string) => ['mastery-summary', projectId] as const }
export const masteryApi = {
  attempt: (projectId: string, payload: { mode: 'outline' | 'flashcards' | 'source_questions' | 'ai_questions'; item_type: TargetType; item_id: number; response?: Record<string, unknown>; correct?: boolean; self_rating?: MasteryLevel }) => request(`/api/projects/${projectId}/study-attempts`, { method: 'POST', body: JSON.stringify(payload) }),
  rate: (projectId: string, targetType: TargetType, targetId: number, level: MasteryLevel) => request<MasteryRecord>(`/api/projects/${projectId}/mastery/${targetType}/${targetId}`, { method: 'PUT', body: JSON.stringify({ level }) }),
  records: (projectId: string, level?: string, targetType?: string) => { const query = new URLSearchParams(); if (level) query.set('level', level); if (targetType) query.set('target_type', targetType); return request<MasteryRecord[]>(`/api/projects/${projectId}/mastery${query.size ? `?${query}` : ''}`) },
  summary: (projectId: string) => request<MasterySummary>(`/api/projects/${projectId}/mastery/summary`),
}
