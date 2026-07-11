import { afterEach, describe, expect, it, vi } from 'vitest'

import { api } from './client'

describe('review API mapping', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('starts a due-only review without a lesson and keeps page provenance', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({
        id: 'review-1',
        lesson_id: null,
        status: 'active',
        started_at: '2026-07-11T12:00:00Z',
        stop_adding_at: '2026-07-11T12:12:00Z',
        hard_deadline_at: '2026-07-11T12:15:00Z',
        questions: [
          {
            id: 'question-1',
            prompt: '为什么要做前烘？',
            source_refs: ['page:page-1'],
            sources: [
              {
                kind: 'page',
                source_ref: 'page:page-1',
                document_id: 'document-1',
                page_id: 'page-1',
                filename: '光刻.pdf',
                page_number: 7,
                preview_url: '/api/pages/page-1/preview',
              },
            ],
            is_bad: false,
          },
        ],
      }),
    })
    vi.stubGlobal('fetch', fetchMock)

    const review = await api.createReviewSession()

    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({})
    expect(review.items[0].source).toMatchObject({
      filename: '光刻.pdf',
      page_number: 7,
      preview_url: '/api/pages/page-1/preview',
    })
  })

  it('maps the scheduled date returned after an answer', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 201,
        json: async () => ({
          outcome: 'reinforce',
          feedback: '需要补充控制限与规格限的区别。',
          question: {
            reference_answer: '控制限来自过程数据。',
            due_at: '2026-07-12T12:00:00Z',
          },
        }),
      }),
    )

    const result = await api.answerReview('review-1', {
      question_id: 'question-1',
      answer: '控制过程波动',
      self_rating: 'fuzzy',
    })

    expect(result.next_review_at).toBe('2026-07-12T12:00:00Z')
  })
})
