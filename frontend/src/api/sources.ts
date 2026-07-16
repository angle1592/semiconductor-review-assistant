import { request } from './client'

export type SourceDocument = {
  id: number
  project_id: string
  display_name: string
  extension: string
  media_type: string
  byte_size: number
  sha256: string
  source_kind: 'questions' | 'reference' | 'mixed'
  parse_status: 'pending' | 'parsed' | 'degraded' | 'failed'
  parser_version: string
  page_count: number | null
  warnings: string[]
  created_at: string
  updated_at: string
}

export type SourceBlock = {
  id: string
  ordinal: number
  locator: string
  kind: string
  text: string
  page_number: number | null
  heading_path: string[]
  preview_path: string | null
}

export type Paged<T> = { items: T[]; total: number; offset: number; limit: number }
export type SourceUploadResult = {
  source_id: number
  parse_status: SourceDocument['parse_status']
  page_count: number | null
  block_count: number
  cache: 'hit' | 'miss'
  warnings: string[]
}

export const sourceKeys = {
  all: (projectId: string) => ['sources', projectId] as const,
  blocks: (sourceId: number) => ['source-blocks', sourceId] as const,
}

export const sourcesApi = {
  list: (projectId: string) => request<Paged<SourceDocument>>(`/api/projects/${projectId}/sources`),
  blocks: (sourceId: number) => request<Paged<SourceBlock>>(`/api/sources/${sourceId}/blocks`),
  upload: (projectId: string, file: File, sourceKind: SourceDocument['source_kind'] = 'mixed') => {
    const form = new FormData()
    form.append('file', file)
    form.append('source_kind', sourceKind)
    return request<SourceUploadResult>(`/api/projects/${projectId}/sources`, { method: 'POST', body: form })
  },
  remove: (sourceId: number) => request<void>(`/api/sources/${sourceId}`, { method: 'DELETE' }),
}
