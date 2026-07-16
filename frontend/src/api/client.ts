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

export type ProviderProtocol = 'openai_compatible' | 'anthropic'

export type ProviderProfile = {
  id: string
  name: string
  protocol: ProviderProtocol
  base_url: string
  enabled: boolean
  is_default: boolean
  credential_generation: number
  api_key_configured: boolean
  models_fetched_at: string | null
  created_at: string
  updated_at: string
}

export type ProviderProfileInput = Pick<ProviderProfile, 'name' | 'protocol' | 'base_url'> & {
  api_key?: string
}

export type ModelProfile = {
  id: string
  provider_id: string
  model_id: string
  display_name: string
  text_status: string
  structured_status: string
  vision_status: string
  prompt_cache_status: string
  safe_error_code: string | null
  validated_at: string | null
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
  listProviders: () => request<ProviderProfile[]>('/api/providers'),
  getProvider: (providerId: string) => request<ProviderProfile>(`/api/providers/${providerId}`),
  createProvider: (payload: ProviderProfileInput) => request<ProviderProfile>('/api/providers', { method: 'POST', body: json(payload) }),
  updateProvider: (providerId: string, payload: Partial<ProviderProfileInput>) => request<ProviderProfile>(`/api/providers/${providerId}`, { method: 'PATCH', body: json(payload) }),
  deleteProvider: (providerId: string) => request<void>(`/api/providers/${providerId}`, { method: 'DELETE' }),
  listModels: (providerId: string) => request<ModelProfile[]>(`/api/providers/${providerId}/models`),
  refreshModels: (providerId: string, force = false) => request<ModelProfile[]>(`/api/providers/${providerId}/models:refresh${force ? '?force=true' : ''}`, { method: 'POST' }),
  addModel: (providerId: string, payload: { model_id: string; display_name: string }) => request<ModelProfile>(`/api/providers/${providerId}/models`, { method: 'POST', body: json(payload) }),
  probeModel: (providerId: string, modelProfileId: string) => request<ModelProfile>(`/api/providers/${providerId}/models/${modelProfileId}:probe`, { method: 'POST' }),
  enableProvider: (providerId: string) => request<ProviderProfile>(`/api/providers/${providerId}:enable`, { method: 'POST' }),
  disableProvider: (providerId: string) => request<ProviderProfile>(`/api/providers/${providerId}:disable`, { method: 'POST' }),
  setDefaultProvider: (providerId: string) => request<ProviderProfile>(`/api/providers/${providerId}:default`, { method: 'POST' }),
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
