import { resolveApiBaseUrl } from './base'

export const API_BASE_URL = resolveApiBaseUrl(
  import.meta.env.VITE_API_BASE_URL,
  import.meta.env.DEV,
  window.location.origin,
)

export type Course = {
  id: string
  title: string
  description: string
}

export type PageSource = {
  document_id: string
  filename: string
  page_number: number
}

export type ReviewSource = {
  kind: 'page' | 'notebook' | 'unknown' | string
  source_ref: string
  filename: string
  document_id?: string
  page_id?: string
  page_number?: number
  preview_url?: string
  notebook_import_id?: string
  title?: string
}

export type CoursePage = {
  id: string
  document_id: string
  page_number: number
  extracted_text: string
  preview_url: string
  source: PageSource
}

export type CourseDocument = {
  id: string
  course_id: string
  title: string
  original_filename: string
  file_type: 'pdf' | 'ppt' | 'pptx' | string
  page_count: number
  created_at: string
  pages: CoursePage[]
}

export type LessonNotes = {
  teacher_emphasis: string
  practical_content: string
  personal_questions: string
}

export type Lesson = {
  id: string
  course_id: string
  title: string
  page_ids: string[]
  notebook_import_ids: string[]
  notes: string
  target_minutes: number
  status: string
  questions?: Array<{ id: string }>
  created_at?: string
}

export type ReviewItem = {
  id: string
  question: string
  reference_answer?: string
  explanation?: string
  source?: ReviewSource
  kind?: 'concept' | 'process' | 'comparison' | 'visual'
}

export type ReviewSession = {
  id: string
  status: 'active' | 'completed' | string
  target_minutes?: number
  hard_limit_minutes?: number
  items: ReviewItem[]
}

export type AnswerResult = {
  assessment?: 'correct' | 'partial' | 'incorrect' | 'unknown'
  mastery?: 'mastered' | 'reinforce' | 'unmastered'
  feedback?: string
  missing_points?: string[]
  next_review_at?: string
  reference_answer?: string
}

type RawReviewSession = {
  id: string
  status: string
  lesson_id: string | null
  started_at: string
  stop_adding_at: string
  hard_deadline_at: string
  questions: Array<{
    id: string
    prompt: string
    source_refs: string[]
    sources?: ReviewSource[]
    is_bad: boolean
  }>
}

type RawAnswerResult = {
  outcome?: 'mastered' | 'reinforce' | 'notMastered'
  feedback?: string
  missing_points?: string[]
  question?: {
    reference_answer?: string
    explanation?: string
    source_refs?: string[]
    due_at?: string
  }
}

export type AISettings = {
  provider: 'openai_compatible' | 'codex'
  base_url: string
  model: string
  api_key_configured?: boolean
  vision_enabled?: boolean
}

export type Dashboard = {
  today_new_lessons: number
  due_count: number
  estimated_minutes: number
  stable_count: number
  reinforce_count: number
  not_mastered_count: number
  weak_points: Array<{
    question_id: string
    prompt: string
    mastery_state: string
  }>
}

export class ApiError extends Error {
  status: number
  code?: string

  constructor(message: string, status: number, code?: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body && !(init.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers })
  if (!response.ok) {
    let problem: { detail?: string; message?: string; code?: string } = {}
    try {
      problem = await response.json()
    } catch {
      // The status text below is more useful than a second parsing error.
    }
    throw new ApiError(
      problem.detail ?? problem.message ?? `请求失败（${response.status}）`,
      response.status,
      problem.code,
    )
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

async function requestBlob(path: string): Promise<Blob> {
  const response = await fetch(`${API_BASE_URL}${path}`)
  if (!response.ok) throw new ApiError(`备份导出失败（${response.status}）`, response.status)
  return response.blob()
}

const json = (value: unknown) => JSON.stringify(value)

export const api = {
  getDashboard: () => request<Dashboard>('/api/dashboard'),
  listCourses: () => request<Course[]>('/api/courses'),
  getCourse: (courseId: string) => request<Course>(`/api/courses/${courseId}`),
  createCourse: (payload: Pick<Course, 'title' | 'description'>) =>
    request<Course>('/api/courses', { method: 'POST', body: json(payload) }),
  listDocuments: (courseId: string) =>
    request<CourseDocument[]>(`/api/courses/${courseId}/documents`),
  getDocument: (documentId: string) => request<CourseDocument>(`/api/documents/${documentId}`),
  uploadDocument: (courseId: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<CourseDocument>(`/api/courses/${courseId}/documents`, {
      method: 'POST',
      body: form,
    })
  },
  importNotebook: (
    courseId: string,
    payload: { title: string; raw_text: string; source_filename?: string },
  ) =>
    request<{ id: string }>(`/api/courses/${courseId}/notebook-imports`, {
      method: 'POST',
      body: json(payload),
    }),
  createLesson: (payload: {
    course_id: string
    title: string
    notes: string
    target_minutes: number
    page_ids: string[]
    notebook_import_ids: string[]
  }) =>
    request<Lesson>('/api/lessons', { method: 'POST', body: json(payload) }),
  generateLesson: (lessonId: string) =>
    request<Lesson>(`/api/lessons/${lessonId}/generate`, {
      method: 'POST',
    }),
  createReviewSession: async (lessonId?: string) => {
    const raw = await request<RawReviewSession>('/api/review-sessions', {
      method: 'POST',
      body: json(lessonId ? { lesson_id: lessonId } : {}),
    })
    return mapReviewSession(raw)
  },
  getReviewSession: async (sessionId: string) =>
    mapReviewSession(await request<RawReviewSession>(`/api/review-sessions/${sessionId}`)),
  answerReview: (
    sessionId: string,
    payload: {
      question_id: string
      answer?: string
      self_rating?: 'certain' | 'fuzzy' | 'unknown'
      skipped?: boolean
      bad_question?: boolean
    },
  ) =>
    request<RawAnswerResult>(`/api/review-sessions/${sessionId}/answers`, {
      method: 'POST',
      body: json({
        question_id: payload.question_id,
        action: payload.bad_question ? 'bad' : payload.skipped ? 'skipped' : 'answered',
        answer_text: payload.answer ?? '',
        self_rating: payload.self_rating,
      }),
    }).then((result) => ({
      mastery:
        result.outcome === 'notMastered'
          ? 'unmastered'
          : result.outcome,
      feedback: result.feedback,
      missing_points: result.missing_points,
      reference_answer: result.question?.reference_answer,
      next_review_at: result.question?.due_at,
    } as AnswerResult)),
  updateQuestion: (questionId: string, prompt: string) =>
    request<{ id: string; prompt: string }>(`/api/questions/${questionId}`, {
      method: 'PATCH',
      body: json({ prompt }),
    }),
  getAISettings: () => request<AISettings>('/api/settings/ai'),
  saveAISettings: (payload: AISettings & { api_key?: string }) =>
    request<AISettings>('/api/settings/ai', { method: 'PUT', body: json(payload) }),
  testAISettings: (payload: AISettings & { api_key?: string }) =>
    request<{ ok: boolean; message?: string; capabilities?: string[] }>('/api/settings/ai/test', {
      method: 'POST',
      body: json(payload),
    }),
  exportBackup: () => requestBlob('/api/backups/export'),
  restoreBackup: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<{ restored: boolean }>('/api/backups/restore', { method: 'POST', body: form })
  },
}

function mapReviewSession(raw: RawReviewSession): ReviewSession {
  return {
    id: raw.id,
    status: raw.status,
    target_minutes: 10,
    hard_limit_minutes: 15,
    items: raw.questions.map((question) => ({
      id: question.id,
      question: question.prompt,
      source: question.sources?.[0],
    })),
  }
}

export function previewUrl(path: string): string {
  return path.startsWith('http') ? path : `${API_BASE_URL}${path}`
}
