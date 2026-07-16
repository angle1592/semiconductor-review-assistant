import { request } from './client'
import type { Importance } from './keypoints'

export type SourceQuestion = { id: number; project_id: string; document_id: number; question_text: string; answer_text: string | null; source_block_ids: string[]; evidence_quotes: string[]; user_edited: boolean; archived: boolean; run_id: number | null; created_at: string; updated_at: string }
export type ArtifactKind = 'outline' | 'flashcard' | 'ai_new' | 'ai_variant' | 'ai_error_cause'
export type Artifact = { id: number; project_id: string; kind: ArtifactKind; status: string; payload: { outline?: { title: string; sections: { heading: string; body: string; keypoint_ids: number[] }[] } | null; flashcards?: { front: string; back: string; keypoint_ids: number[] }[]; questions?: { question: string; answer: string; explanation: string; origin: string; source_question_ids: number[]; keypoint_ids: number[] }[] }; keypoint_ids: number[]; source_question_ids: number[]; cache_status: string | null; public_error_code: string | null; error_detail: string | null; created_at: string; updated_at: string }
export type ArtifactCreate = { kind: ArtifactKind; keypoint_ids: number[]; source_question_ids: number[]; provider_id: string; model_profile_id: string; run_override: string }

export const studyKeys = { questions: (projectId: string) => ['source-questions', projectId] as const, artifacts: (projectId: string) => ['artifacts', projectId] as const, artifact: (id: number) => ['artifact', id] as const }
export const studyApi = {
  questions: (projectId: string) => request<SourceQuestion[]>(`/api/projects/${projectId}/source-questions`),
  updateQuestion: (id: number, payload: { question_text?: string; answer_text?: string | null }) => request<SourceQuestion>(`/api/source-questions/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  archiveQuestion: (id: number) => request<SourceQuestion>(`/api/source-questions/${id}/archive`, { method: 'POST' }),
  artifacts: (projectId: string) => request<Artifact[]>(`/api/projects/${projectId}/artifacts`),
  artifact: (id: number) => request<Artifact>(`/api/artifacts/${id}`),
  generate: (projectId: string, payload: ArtifactCreate) => request<Artifact>(`/api/projects/${projectId}/artifacts`, { method: 'POST', body: JSON.stringify(payload) }),
  removeArtifact: (id: number) => request<void>(`/api/artifacts/${id}`, { method: 'DELETE' }),
}

export type ReviewSelection = { id: number; title: string; explanation: string; importance: Importance }
