import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'

import type { Artifact, SourceQuestion } from '../../api/study'
import { StudySessionPage } from './StudySessionPage'

afterEach(() => vi.unstubAllGlobals())

it('reveals cards intentionally and records an explicit self-rating', async () => {
  const user = userEvent.setup()
  const bodies: unknown[] = []
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async (_input: RequestInfo | URL, init?: RequestInit) => {
    bodies.push(JSON.parse(String(init?.body)))
    return response({ id: 1 })
  }))

  renderSession(<StudySessionPage projectId="project-1" artifact={flashcards} onClose={() => undefined} />)

  expect(screen.getByText('什么是带隙？')).toBeInTheDocument()
  expect(screen.queryByText('导带底与价带顶的能量差')).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: '显示答案' }))
  expect(screen.getByText('导带底与价带顶的能量差')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: '已熟悉' }))
  expect(await screen.findByText('本次复习记录已保存。')).toBeInTheDocument()
  expect(bodies[0]).toMatchObject({ mode: 'flashcards', item_type: 'artifact', item_id: 8, self_rating: 'familiar' })
})

it('keeps a written answer local until reveal and records correctness', async () => {
  const user = userEvent.setup()
  const bodies: unknown[] = []
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async (_input: RequestInfo | URL, init?: RequestInit) => {
    bodies.push(JSON.parse(String(init?.body)))
    return response({ id: 2 })
  }))

  renderSession(<StudySessionPage projectId="project-1" sourceQuestion={sourceQuestion} onClose={() => undefined} />)

  await user.type(screen.getByLabelText('我的答案'), '我的本地草稿')
  expect(screen.queryByText('参考答案')).not.toBeInTheDocument()
  expect(bodies).toHaveLength(0)
  await user.click(screen.getByRole('button', { name: '核对答案' }))
  expect(screen.getByText('参考答案')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: '我答对了' }))
  expect(bodies[0]).toMatchObject({ mode: 'source_questions', item_type: 'source_question', item_id: 11, correct: true })
  expect(JSON.stringify(bodies[0])).not.toContain('我的本地草稿')
})

function renderSession(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  render(<QueryClientProvider client={client}>{node}</QueryClientProvider>)
}

function response(value: unknown) {
  return { ok: true, status: 200, json: async () => value }
}

const flashcards: Artifact = {
  id: 8, project_id: 'project-1', kind: 'flashcard', status: 'succeeded',
  payload: { flashcards: [{ front: '什么是带隙？', back: '导带底与价带顶的能量差', keypoint_ids: [3] }] },
  keypoint_ids: [3], source_question_ids: [], cache_status: 'miss', public_error_code: null, error_detail: null, created_at: '', updated_at: '',
}

const sourceQuestion: SourceQuestion = {
  id: 11, project_id: 'project-1', document_id: 2, question_text: '解释带隙。', answer_text: '能带之间的能量差。',
  source_block_ids: ['b1'], evidence_quotes: [], user_edited: false, archived: false, run_id: 4, created_at: '', updated_at: '',
}
