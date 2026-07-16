import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'

import { MaterialsPage } from './MaterialsPage'


afterEach(() => vi.unstubAllGlobals())

it('explains supported files and uploads from both picker and drop zone', async () => {
  const user = userEvent.setup()
  let uploaded = false
  const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.includes('/sources') && init?.method === 'POST') {
      uploaded = true
      return { ok: true, status: 201, json: async () => ({ source_id: 1, parse_status: 'degraded', page_count: 2, block_count: 3, cache: 'miss', warnings: ['PPTX 预览不可用'] }) }
    }
    if (url.endsWith('/api/projects/project-1/sources')) {
      return { ok: true, status: 200, json: async () => ({ items: uploaded ? [{ id: 1, project_id: 'project-1', display_name: '复习资料.pptx', extension: '.pptx', media_type: 'application/vnd.openxmlformats-officedocument.presentationml.presentation', byte_size: 1200, sha256: 'sha', source_kind: 'mixed', parse_status: 'degraded', parser_version: '1', page_count: 2, warnings: ['PPTX 预览不可用'], created_at: '2026-07-16T12:00:00Z', updated_at: '2026-07-16T12:00:00Z' }] : [], total: uploaded ? 1 : 0, offset: 0, limit: 20 }) }
    }
    if (url.endsWith('/api/sources/1/blocks')) {
      return { ok: true, status: 200, json: async () => ({ items: [], total: 0, offset: 0, limit: 100 }) }
    }
    throw new Error(`Unexpected request: ${url}`)
  })
  vi.stubGlobal('fetch', fetchMock)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

  render(
    <QueryClientProvider client={client}>
      <MaterialsPage projectId="project-1" selectedBlockIds={[]} onSelectedBlockIdsChange={() => undefined} />
    </QueryClientProvider>,
  )

  expect(await screen.findByText(/支持 PDF、Word、PPT、TXT 和 Markdown/)).toBeInTheDocument()
  expect(screen.getByText(/单个文件最多 100 MB/)).toBeInTheDocument()
  const file = new File(['slides'], '复习资料.pptx', { type: 'application/vnd.openxmlformats-officedocument.presentationml.presentation' })
  await user.upload(screen.getByLabelText('选择资料文件'), file)

  expect(await screen.findByText('复习资料.pptx')).toBeInTheDocument()
  expect(screen.getByText('解析完成，但有提醒')).toBeInTheDocument()
  expect(screen.getByText('PPTX 预览不可用')).toBeInTheDocument()

  fireEvent.drop(screen.getByTestId('source-drop-zone'), { dataTransfer: { files: [file] } })
  await waitFor(() => expect(fetchMock).toHaveBeenCalled())
})

