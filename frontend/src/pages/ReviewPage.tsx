import { useEffect, useRef, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { AlertTriangle, ArrowRight, CheckCircle2, Clock3, Eye, Flag, Pencil, SkipForward } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'

import { api, ApiError, previewUrl, type AnswerResult, type ReviewSession } from '../api/client'
import { WaferStages } from '../components/WaferStages'

type SelfRating = 'certain' | 'fuzzy' | 'unknown'

const ratingLabels: Record<SelfRating, string> = {
  certain: '确定',
  fuzzy: '模糊',
  unknown: '不会',
}

function formatReviewDate(value?: string): string {
  if (!value) return '暂无排期'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '暂无排期'
  return `${date.getFullYear()} 年 ${date.getMonth() + 1} 月 ${date.getDate()} 日`
}

export function ReviewPage() {
  const [searchParams] = useSearchParams()
  const lessonId = searchParams.get('lesson') ?? ''
  const [session, setSession] = useState<ReviewSession | null>(null)
  const [index, setIndex] = useState(0)
  const [answer, setAnswer] = useState('')
  const [feedback, setFeedback] = useState<AnswerResult | null>(null)
  const [sourceOpen, setSourceOpen] = useState(false)
  const [editing, setEditing] = useState(false)
  const [editedPrompt, setEditedPrompt] = useState('')
  const [elapsed, setElapsed] = useState(0)
  const [finished, setFinished] = useState(false)
  const [results, setResults] = useState<AnswerResult[]>([])
  const [skippedCount, setSkippedCount] = useState(0)
  const startedAt = useRef(0)
  const start = useMutation({
    mutationFn: () => api.createReviewSession(lessonId || undefined),
    onSuccess: (next) => {
      setSession(next)
      setIndex(0)
      setAnswer('')
      setFeedback(null)
      setEditing(false)
      setResults([])
      setSkippedCount(0)
      setElapsed(0)
      setFinished(false)
      startedAt.current = Date.now()
    },
  })
  const submit = useMutation({
    mutationFn: (payload: Parameters<typeof api.answerReview>[1]) => api.answerReview(session!.id, payload),
  })
  const edit = useMutation({
    mutationFn: ({ questionId, prompt }: { questionId: string; prompt: string }) => api.updateQuestion(questionId, prompt),
    onSuccess: (updated) => {
      setSession((current) => current ? {
        ...current,
        items: current.items.map((candidate) => candidate.id === updated.id ? { ...candidate, question: updated.prompt } : candidate),
      } : current)
      setEditing(false)
    },
  })

  useEffect(() => {
    if (!session || finished) return undefined
    const updateElapsed = () => {
      const seconds = Math.max(0, Math.floor((Date.now() - startedAt.current) / 1000))
      setElapsed(Math.min(900, seconds))
      if (seconds >= 900) setFinished(true)
    }
    updateElapsed()
    const timer = window.setInterval(updateElapsed, 1000)
    return () => window.clearInterval(timer)
  }, [session, finished])

  const item = session?.items[index]
  const progress = session?.items.length ? ((index + (feedback ? 1 : 0)) / session.items.length) * 100 : 0
  const minutes = Math.floor(elapsed / 60).toString().padStart(2, '0')
  const seconds = (elapsed % 60).toString().padStart(2, '0')

  async function rate(selfRating: SelfRating) {
    if (!item) return
    try {
      const result = await submit.mutateAsync({ question_id: item.id, answer, self_rating: selfRating })
      setFeedback(result)
      setResults((current) => [...current, result])
    } catch (error) {
      if (error instanceof ApiError && error.code === 'REVIEW_SESSION_EXPIRED') {
        setElapsed(900)
        setFinished(true)
      }
    }
  }

  async function skip(badQuestion = false) {
    if (!item) return
    try {
      await submit.mutateAsync({ question_id: item.id, skipped: true, bad_question: badQuestion })
      setSkippedCount((current) => current + 1)
      advance()
    } catch (error) {
      if (error instanceof ApiError && error.code === 'REVIEW_SESSION_EXPIRED') {
        setElapsed(900)
        setFinished(true)
      }
    }
  }

  const weakCount = results.filter((result) => result.mastery !== 'mastered').length
  const nextReviewAt = results
    .map((result) => result.next_review_at)
    .filter((value): value is string => Boolean(value))
    .sort((left, right) => new Date(left).getTime() - new Date(right).getTime())[0]
  const completedCount = results.length + skippedCount

  function advance() {
    if (!session || index >= session.items.length - 1) {
      setFinished(true)
      return
    }
    setIndex((current) => current + 1)
    setAnswer('')
    setFeedback(null)
    setSourceOpen(false)
    setEditing(false)
  }

  if (!session && !finished) {
    return (
      <div className="review-entry review-column">
        <div className="review-entry-mark" aria-hidden="true"><Clock3 /></div>
        <p className="eyebrow">主动回忆 · 最长 15 分钟</p>
        <h1>把答案从脑中拿出来，再看课件</h1>
        <p>新课至少四题，其余位置补到期薄弱点；单次最多八题，12 分钟后不会再加新题。</p>
        <WaferStages active={0} compact />
        {start.isError && (
          <div className="notice notice--error" role="alert">复习队列暂时不可用。已有题目仍可在本地服务恢复后继续，自评排期不会丢失。</div>
        )}
        {!lessonId && <div className="notice">将从所有课程中按到期时间抽取最多 8 道题；没有到期题时会立即结束。</div>}
        <button className="button button--primary button--large" type="button" onClick={() => start.mutate()} disabled={start.isPending}>
          {start.isPending ? '正在准备题目…' : '开始本次复习'} <ArrowRight aria-hidden="true" />
        </button>
      </div>
    )
  }

  if (finished || !item) {
    return (
      <div className="completion-panel review-column">
        <span className="completion-icon"><CheckCircle2 aria-hidden="true" /></span>
        <p className="eyebrow">本次复习结束</p>
        <h1>{elapsed >= 900 ? '十五分钟到了，准时收尾' : '今天的回忆已完成'}</h1>
        <p>掌握度与下次日期已写回本机。坏题和跳过题不会影响掌握度。</p>
        <div className="result-summary">
          <div><span>完成题数</span><strong>{completedCount}</strong></div>
          <div><span>用时</span><strong>{minutes}:{seconds}</strong></div>
          <div><span>本次薄弱点</span><strong>待巩固 {weakCount} 题</strong></div>
          <div><span>最近下次复习</span><strong>{formatReviewDate(nextReviewAt)}</strong></div>
        </div>
        <a className="button button--primary" href="/progress">查看掌握进度</a>
      </div>
    )
  }

  return (
    <div className="review-column review-workspace">
      <header className="review-toolbar">
        <div>
          <span>问题 {index + 1} / {session.items.length}</span>
          <div className="progress-track"><span style={{ width: `${progress}%` }} /></div>
        </div>
        <div className={`review-timer${elapsed >= 720 ? ' is-warning' : ''}`}>
          <Clock3 aria-hidden="true" /><span>{minutes}:{seconds}</span>
        </div>
      </header>
      {elapsed >= 720 && <div className="time-warning"><AlertTriangle aria-hidden="true" />已停止加入新题，完成当前题后收尾。</div>}

      <article className="question-card">
        <div className="question-meta">
          <span className="question-kind">{item.kind === 'visual' ? '图片理解' : item.kind === 'comparison' ? '流程与对比' : '概念解释'}</span>
          {item.source && (
            <span>
              来源 · {item.source.filename}
              {item.source.page_number ? ` P.${item.source.page_number}` : ''}
            </span>
          )}
        </div>
        {editing ? (
          <form
            className="question-editor"
            onSubmit={(event) => {
              event.preventDefault()
              const prompt = editedPrompt.trim()
              if (prompt) edit.mutate({ questionId: item.id, prompt })
            }}
          >
            <label>
              <span>题目内容</span>
              <textarea aria-label="题目内容" rows={4} value={editedPrompt} onChange={(event) => setEditedPrompt(event.target.value)} autoFocus />
            </label>
            <div>
              <button className="button button--ghost" type="button" onClick={() => setEditing(false)} disabled={edit.isPending}>取消</button>
              <button className="button button--secondary" type="submit" disabled={!editedPrompt.trim() || edit.isPending}>{edit.isPending ? '正在保存…' : '保存修改'}</button>
            </div>
            {edit.isError && <p className="form-error">题目修改未保存，请检查本地服务后重试。</p>}
          </form>
        ) : <h1>{item.question}</h1>}
        {!feedback ? (
          <>
            <label className="answer-field">
              <span>用自己的话回答</span>
              <textarea value={answer} onChange={(event) => setAnswer(event.target.value)} rows={7} autoFocus placeholder="先回忆，再组织关键点。简短答案也可以。" />
            </label>
            <div className="review-actions-row">
              <div className="question-tools">
                <button type="button" className="button button--ghost" disabled={submit.isPending} onClick={() => void skip(false)}><SkipForward /> 跳过</button>
                <button type="button" className="button button--ghost" disabled={submit.isPending || editing} onClick={() => { setEditedPrompt(item.question); setEditing(true) }}><Pencil /> 修改题目</button>
                <button type="button" className="button button--ghost" disabled={submit.isPending} onClick={() => void skip(true)}><Flag /> 标记坏题</button>
              </div>
              <div className="self-rating" aria-label="回答把握程度">
                <span>我的把握</span>
                {(Object.keys(ratingLabels) as SelfRating[]).map((rating) => (
                  <button type="button" key={rating} disabled={(rating !== 'unknown' && !answer.trim()) || submit.isPending} onClick={() => void rate(rating)}>{ratingLabels[rating]}</button>
                ))}
              </div>
            </div>
            {submit.isError && <p className="form-error">答案未保存。连接恢复前请保留当前页面，不会自动切换后端。</p>}
          </>
        ) : (
          <div className="feedback-panel">
            <div className="feedback-heading">
              <span className={`status-chip ${feedback.mastery === 'mastered' ? 'status-chip--teal' : 'status-chip--amber'}`}>
                {feedback.mastery === 'mastered' ? '掌握' : feedback.mastery === 'unmastered' ? '未掌握' : '待巩固'}
              </span>
              <strong>{feedback.feedback || '自评已记录，排期已更新。'}</strong>
            </div>
            {feedback.missing_points && feedback.missing_points.length > 0 && (
              <div><p className="eyebrow">遗漏点</p><ul>{feedback.missing_points.map((point) => <li key={point}>{point}</li>)}</ul></div>
            )}
            {(feedback.reference_answer || item.reference_answer) && <div className="reference-answer"><p className="eyebrow">参考答案</p><p>{feedback.reference_answer || item.reference_answer}</p></div>}
            <div className="feedback-footer">
              {item.source && <button className="button button--secondary" type="button" onClick={() => setSourceOpen((open) => !open)}><Eye /> {sourceOpen ? '收起来源' : '查看来源'}</button>}
              <button className="button button--primary" type="button" onClick={advance}>{index === session.items.length - 1 ? '完成复习' : '下一题'} <ArrowRight /></button>
            </div>
            {sourceOpen && item.source && (
              <figure className="source-note">
                {item.source.preview_url && <img src={previewUrl(item.source.preview_url)} alt={`${item.source.filename} 第 ${item.source.page_number} 页`} />}
                <figcaption>
                  {item.source.filename}
                  {item.source.page_number ? ` · 第 ${item.source.page_number} 页` : ''}
                  。系统只使用了该来源与课堂补充。
                </figcaption>
              </figure>
            )}
          </div>
        )}
      </article>
    </div>
  )
}
