import { resolveApiBaseUrl } from './base'

export const API_BASE_URL = resolveApiBaseUrl(
  import.meta.env.VITE_API_BASE_URL,
  import.meta.env.DEV,
  window.location.origin,
)

export type ReviewProject = {
  id: string
  name: string
  description: string
  importance_prompt: string
  created_at: string
  updated_at: string
}

export type ReviewProjectInput = Pick<ReviewProject, 'name' | 'description' | 'importance_prompt'>

export type AISettings = {
  provider: 'openai_compatible'
  base_url: string
  model: string
  api_key_configured?: boolean
  vision_enabled: boolean
}

export type AISettingsInput = AISettings & {
  api_key?: string
  clear_api_key?: boolean
}

export type ConnectionTestResult = {
  ok: boolean
  message?: string
  capabilities?: string[]
}

export type SystemInfo = {
  application: string
  version: string
  packaged: boolean
  setup_complete: boolean
  data_directory: string
  log_directory: string
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
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json')

  const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers })
  if (!response.ok) {
    let problem: { detail?: string; message?: string; code?: string } = {}
    try {
      problem = await response.json()
    } catch {
      // Fall back to a stable local message when an upstream response has no JSON body.
    }
    throw new ApiError(
      problem.message ?? problem.detail ?? `请求失败（${response.status}）`,
      response.status,
      problem.code,
    )
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

async function requestBlob(path: string): Promise<Blob> {
  const response = await fetch(`${API_BASE_URL}${path}`)
  if (!response.ok) throw new ApiError(`文件导出失败（${response.status}）`, response.status)
  return response.blob()
}

const json = (value: unknown) => JSON.stringify(value)

export const api = {
  listProjects: () => request<ReviewProject[]>('/api/projects'),
  getProject: (projectId: string) => request<ReviewProject>(`/api/projects/${projectId}`),
  createProject: (payload: ReviewProjectInput) =>
    request<ReviewProject>('/api/projects', { method: 'POST', body: json(payload) }),
  updateProject: (projectId: string, payload: Partial<ReviewProjectInput>) =>
    request<ReviewProject>(`/api/projects/${projectId}`, { method: 'PATCH', body: json(payload) }),
  deleteProject: (projectId: string) =>
    request<void>(`/api/projects/${projectId}`, { method: 'DELETE' }),
  getAISettings: () => request<AISettings>('/api/settings/ai'),
  saveAISettings: (payload: AISettingsInput) =>
    request<AISettings>('/api/settings/ai', { method: 'PUT', body: json(payload) }),
  testAISettings: (payload: AISettingsInput) =>
    request<ConnectionTestResult>('/api/settings/ai/test', { method: 'POST', body: json(payload) }),
  exportBackup: () => requestBlob('/api/backups/export'),
  restoreBackup: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<{ restored: boolean }>('/api/backups/restore', { method: 'POST', body: form })
  },
  getSystemInfo: () => request<SystemInfo>('/api/system/info'),
  completeSetup: () => request<void>('/api/system/setup-complete', { method: 'POST' }),
  openSystemPath: (kind: 'data' | 'backups' | 'logs') =>
    request<void>(`/api/system/paths/${kind}/open`, { method: 'POST' }),
  exportDiagnostics: () => requestBlob('/api/system/diagnostics'),
  shutdown: () => request<{ status: string }>('/api/system/shutdown', { method: 'POST' }),
}

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}
