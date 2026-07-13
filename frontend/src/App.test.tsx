import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AppRoutes } from './App'

describe('application shell', () => {
  it('shows the review-first dashboard navigation', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <AppRoutes />
      </MemoryRouter>,
    )

    expect(screen.getByRole('heading', { name: '今天，先把课堂留下来' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '课程' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '开始复习' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '设置' })).toBeInTheDocument()
  })

  it('shows live due and weak-point data on the dashboard', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          today_new_lessons: 1,
          due_count: 3,
          estimated_minutes: 6,
          weak_points: [{ question_id: 'q1', prompt: '解释控制限', mastery_state: 'reinforce' }],
        }),
      }),
    )

    render(
      <MemoryRouter initialEntries={['/']}>
        <AppRoutes />
      </MemoryRouter>,
    )

    expect(await screen.findByText('3')).toBeInTheDocument()
    expect(screen.getByText('解释控制限')).toBeInTheDocument()
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('turns an empty course list into a clear next action', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [],
      }),
    )

    render(
      <MemoryRouter initialEntries={['/courses']}>
        <AppRoutes />
      </MemoryRouter>,
    )

    expect(await screen.findByText('还没有课程')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '创建第一门课程' })).toBeInTheDocument()
  })

  it('explains how to recover when courses cannot be loaded', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))

    render(
      <MemoryRouter initialEntries={['/courses']}>
        <AppRoutes />
      </MemoryRouter>,
    )

    expect(await screen.findByText('课程暂时无法读取')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '重新加载' })).toBeInTheDocument()
  })

  it('permanently deletes an imported document after confirmation', async () => {
    const user = userEvent.setup()
    let deleted = false
    const fetchMock = vi.fn().mockImplementation(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input)
        if (url.endsWith('/api/courses/course-1')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ id: 'course-1', title: '晶圆制造', description: '' }),
          }
        }
        if (url.endsWith('/api/courses/course-1/documents')) {
          return {
            ok: true,
            status: 200,
            json: async () =>
              deleted
                ? []
                : [
                    {
                      id: 'document-1',
                      course_id: 'course-1',
                      title: '测试课件',
                      original_filename: '测试课件.pdf',
                      file_type: 'pdf',
                      page_count: 2,
                      created_at: '2026-07-11T12:00:00Z',
                      pages: [],
                    },
                  ],
          }
        }
        if (url.endsWith('/api/documents/document-1') && init?.method === 'DELETE') {
          deleted = true
          return { ok: true, status: 204 }
        }
        throw new Error(`Unexpected request: ${url}`)
      },
    )
    const confirm = vi.fn(() => true)
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('confirm', confirm)

    render(
      <MemoryRouter initialEntries={['/courses/course-1']}>
        <AppRoutes />
      </MemoryRouter>,
    )

    await user.click(
      await screen.findByRole('button', { name: '删除课件 测试课件.pdf' }),
    )

    expect(confirm).toHaveBeenCalledWith(
      expect.stringContaining('相关课次、题目、答案和复习记录也会一并删除'),
    )
    expect(await screen.findByText('已删除 测试课件.pdf。')).toBeInTheDocument()
    expect(screen.queryByText('测试课件.pdf')).not.toBeInTheDocument()
  })

  it('permanently deletes a course and its learning history after confirmation', async () => {
    const user = userEvent.setup()
    let deleted = false
    const fetchMock = vi.fn().mockImplementation(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input)
        if (url.endsWith('/api/courses/course-1') && init?.method === 'DELETE') {
          deleted = true
          return { ok: true, status: 204 }
        }
        if (url.endsWith('/api/courses') && !init?.method) {
          return {
            ok: true,
            status: 200,
            json: async () =>
              deleted
                ? []
                : [{ id: 'course-1', title: '测试课程', description: '待删除' }],
          }
        }
        throw new Error(`Unexpected request: ${url}`)
      },
    )
    const confirm = vi.fn(() => true)
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('confirm', confirm)

    render(
      <MemoryRouter initialEntries={['/courses']}>
        <AppRoutes />
      </MemoryRouter>,
    )

    await user.click(await screen.findByRole('button', { name: '删除课程 测试课程' }))

    expect(confirm).toHaveBeenCalledWith(
      expect.stringContaining('课件、课次、题目、答案和复习记录都会一并删除'),
    )
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/courses/course-1'),
      expect.objectContaining({ method: 'DELETE' }),
    )
    expect(await screen.findByText('已删除课程“测试课程”。')).toBeInTheDocument()
    expect(screen.queryByText('测试课程')).not.toBeInTheDocument()
  })

  it('keeps a course when deletion is cancelled', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [{ id: 'course-1', title: '保留课程', description: '' }],
    })
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('confirm', vi.fn(() => false))

    render(
      <MemoryRouter initialEntries={['/courses']}>
        <AppRoutes />
      </MemoryRouter>,
    )

    await user.click(await screen.findByRole('button', { name: '删除课程 保留课程' }))

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('heading', { name: '保留课程' })).toBeInTheDocument()
  })

  it('keeps a course and shows a safe error when deletion fails', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.fn().mockImplementation(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input)
        if (url.endsWith('/api/courses/course-1') && init?.method === 'DELETE') {
          return {
            ok: false,
            status: 500,
            json: async () => ({ detail: 'internal database details' }),
          }
        }
        return {
          ok: true,
          status: 200,
          json: async () => [{ id: 'course-1', title: '删除失败课程', description: '' }],
        }
      },
    )
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('confirm', vi.fn(() => true))

    render(
      <MemoryRouter initialEntries={['/courses']}>
        <AppRoutes />
      </MemoryRouter>,
    )

    await user.click(await screen.findByRole('button', { name: '删除课程 删除失败课程' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      '课程删除失败，请确认本地服务正在运行后重试。',
    )
    expect(screen.queryByText('internal database details')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '删除失败课程' })).toBeInTheDocument()
  })

  it('starts a due review directly from the main navigation', async () => {
    const user = userEvent.setup()
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
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
              id: 'q1',
              prompt: '说明前烘的目的。',
              source_refs: [],
              sources: [],
              is_bad: false,
            },
          ],
        }),
      }),
    )

    render(
      <MemoryRouter initialEntries={['/review']}>
        <AppRoutes />
      </MemoryRouter>,
    )

    const start = screen.getByRole('button', { name: /开始本次复习/ })
    expect(start).toBeEnabled()
    await user.click(start)
    expect(await screen.findByRole('heading', { name: '说明前烘的目的。' })).toBeInTheDocument()
  })

  it('summarizes the actual weak count and next review date', async () => {
    const user = userEvent.setup()
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 201,
        json: async () => ({
          id: 'review-1',
          lesson_id: null,
          status: 'active',
          started_at: '2026-07-11T12:00:00Z',
          stop_adding_at: '2026-07-11T12:12:00Z',
          hard_deadline_at: '2026-07-11T12:15:00Z',
          questions: [{ id: 'q1', prompt: '解释控制限。', source_refs: [], sources: [], is_bad: false }],
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 201,
        json: async () => ({
          outcome: 'reinforce',
          feedback: '还需区分规格限。',
          question: {
            reference_answer: '控制限由稳定过程的数据计算得到。',
            due_at: '2026-07-12T12:00:00Z',
          },
        }),
      })
    vi.stubGlobal('fetch', fetchMock)

    render(
      <MemoryRouter initialEntries={['/review']}>
        <AppRoutes />
      </MemoryRouter>,
    )

    await user.click(screen.getByRole('button', { name: /开始本次复习/ }))
    await user.type(await screen.findByRole('textbox', { name: '用自己的话回答' }), '来自过程数据。')
    await user.click(screen.getByRole('button', { name: '模糊' }))
    await user.click(await screen.findByRole('button', { name: /完成复习/ }))

    expect(await screen.findByText('待巩固 1 题')).toBeInTheDocument()
    expect(screen.getByText('2026 年 7 月 12 日')).toBeInTheDocument()
  })

  it('lets the learner repair a bad prompt without affecting mastery', async () => {
    const user = userEvent.setup()
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 201,
        json: async () => ({
          id: 'review-1',
          lesson_id: null,
          status: 'active',
          started_at: '2026-07-11T12:00:00Z',
          stop_adding_at: '2026-07-11T12:12:00Z',
          hard_deadline_at: '2026-07-11T12:15:00Z',
          questions: [{ id: 'q1', prompt: '含糊的问题', source_refs: [], sources: [], is_bad: false }],
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ id: 'q1', prompt: '修正后的问题', is_bad: false }),
      })
    vi.stubGlobal('fetch', fetchMock)

    render(
      <MemoryRouter initialEntries={['/review']}>
        <AppRoutes />
      </MemoryRouter>,
    )

    await user.click(screen.getByRole('button', { name: /开始本次复习/ }))
    await user.click(await screen.findByRole('button', { name: '修改题目' }))
    const prompt = screen.getByRole('textbox', { name: '题目内容' })
    await user.clear(prompt)
    await user.type(prompt, '修正后的问题')
    await user.click(screen.getByRole('button', { name: '保存修改' }))

    expect(await screen.findByRole('heading', { name: '修正后的问题' })).toBeInTheDocument()
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ prompt: '修正后的问题' })
  })

  it('allows a genuine cannot-answer rating without placeholder text', async () => {
    const user = userEvent.setup()
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce({
          ok: true,
          status: 201,
          json: async () => ({
            id: 'review-1',
            lesson_id: null,
            status: 'active',
            started_at: new Date().toISOString(),
            stop_adding_at: new Date(Date.now() + 12 * 60_000).toISOString(),
            hard_deadline_at: new Date(Date.now() + 15 * 60_000).toISOString(),
            questions: [{ id: 'q1', prompt: '什么是 overlay？', source_refs: [], sources: [], is_bad: false }],
          }),
        })
        .mockResolvedValueOnce({
          ok: true,
          status: 201,
          json: async () => ({
            outcome: 'notMastered',
            feedback: '',
            question: { reference_answer: '层间图形的对准误差。', due_at: '2026-07-12T12:00:00Z' },
          }),
        }),
    )

    render(
      <MemoryRouter initialEntries={['/review']}>
        <AppRoutes />
      </MemoryRouter>,
    )

    await user.click(screen.getByRole('button', { name: /开始本次复习/ }))
    const cannotAnswer = await screen.findByRole('button', { name: '不会' })
    expect(cannotAnswer).toBeEnabled()
    await user.click(cannotAnswer)
    expect(await screen.findByText('未掌握')).toBeInTheDocument()
  })

  it('retries generation on the saved lesson instead of duplicating the class record', async () => {
    const user = userEvent.setup()
    let lessonCreates = 0
    let generationCalls = 0
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input)
        if (url.endsWith('/api/courses') && !init?.method) {
          return { ok: true, status: 200, json: async () => [{ id: 'course-1', title: '晶圆制造', description: '' }] }
        }
        if (url.endsWith('/api/lessons') && init?.method === 'POST') {
          lessonCreates += 1
          return { ok: true, status: 201, json: async () => ({ id: 'lesson-1', questions: [] }) }
        }
        if (url.endsWith('/api/lessons/lesson-1/generate')) {
          generationCalls += 1
          if (generationCalls === 1) {
            return { ok: false, status: 503, json: async () => ({ code: 'AI_PROVIDER_UNAVAILABLE', message: 'offline' }) }
          }
          return { ok: true, status: 200, json: async () => ({ id: 'lesson-1', questions: [{ id: 'q1' }, { id: 'q2' }, { id: 'q3' }, { id: 'q4' }] }) }
        }
        throw new Error(`Unexpected request: ${url}`)
      }),
    )

    render(
      <MemoryRouter initialEntries={['/lessons/new?course=course-1&notebook=note-1']}>
        <AppRoutes />
      </MemoryRouter>,
    )

    await user.click(await screen.findByRole('button', { name: '保存并生成复习题' }))
    expect(await screen.findByRole('button', { name: '重新生成题目' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '重新生成题目' }))

    expect(await screen.findByRole('heading', { name: '今天的复习入口准备好了' })).toBeInTheDocument()
    expect(lessonCreates).toBe(1)
    expect(generationCalls).toBe(2)
  })
})
