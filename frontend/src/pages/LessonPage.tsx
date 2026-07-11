import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Check, FileStack, Sparkles } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'

import { api, type LessonNotes } from '../api/client'
import { PageHeading } from '../components/Ui'
import { parsePageNumbers } from '../lib/pages'

const blankNotes: LessonNotes = {
  teacher_emphasis: '',
  practical_content: '',
  personal_questions: '',
}

export function LessonPage() {
  const [searchParams] = useSearchParams()
  const initialCourse = searchParams.get('course') ?? ''
  const initialDocument = searchParams.get('document') ?? ''
  const initialNotebook = searchParams.get('notebook') ?? ''
  const [courseId, setCourseId] = useState(initialCourse)
  const [documentId, setDocumentId] = useState(initialDocument)
  const [selectedPages, setSelectedPages] = useState<number[]>([])
  const [manualPages, setManualPages] = useState('')
  const [notes, setNotes] = useState(blankNotes)
  const [result, setResult] = useState<{ lessonId: string; generated?: number } | null>(null)
  const [savedLessonId, setSavedLessonId] = useState('')
  const courses = useQuery({ queryKey: ['courses'], queryFn: api.listCourses })
  const document = useQuery({
    queryKey: ['document', documentId],
    queryFn: () => api.getDocument(documentId),
    enabled: Boolean(documentId),
  })
  const saveLesson = useMutation({
    mutationFn: async () => {
      let lessonId = savedLessonId
      if (!lessonId) {
        const pageNumbers = selectedPages.length > 0 ? selectedPages : parsePageNumbers(manualPages)
        const pageIds = (document.data?.pages ?? [])
          .filter((page) => pageNumbers.includes(page.page_number))
          .map((page) => page.id)
        const lesson = await api.createLesson({
          course_id: courseId,
          title: `课后复习 · ${new Date().toLocaleDateString('zh-CN')}`,
          page_ids: pageIds,
          notebook_import_ids: initialNotebook ? [initialNotebook] : [],
          target_minutes: 10,
          notes: [
            notes.teacher_emphasis && `老师强调：${notes.teacher_emphasis}`,
            notes.practical_content && `实践内容：${notes.practical_content}`,
            notes.personal_questions && `个人疑问：${notes.personal_questions}`,
          ].filter(Boolean).join('\n'),
        })
        lessonId = lesson.id
        setSavedLessonId(lessonId)
      }
      const generated = await api.generateLesson(lessonId)
      return { lessonId, generated: generated.questions?.length ?? 0 }
    },
    onSuccess: setResult,
  })
  const availablePages = document.data?.pages ?? []
  const finalPages = selectedPages.length > 0 ? selectedPages : parsePageNumbers(manualPages)

  function togglePage(pageNumber: number) {
    setSelectedPages((current) =>
      current.includes(pageNumber)
        ? current.filter((page) => page !== pageNumber)
        : [...current, pageNumber].sort((a, b) => a - b),
    )
  }

  function updateNote(field: keyof LessonNotes, value: string) {
    setNotes((current) => ({ ...current, [field]: value }))
  }

  if (result) {
    return (
      <div className="completion-panel">
        <span className="completion-icon"><Check aria-hidden="true" /></span>
        <p className="eyebrow">课堂已归档</p>
        <h1>今天的复习入口准备好了</h1>
        <p>已生成 {result.generated ?? 0} 道带来源的问题；如果 AI 暂时不可用，课堂记录仍已安全保存在本机。</p>
        <div className="form-actions">
          <Link className="button button--primary" to={`/review?lesson=${result.lessonId}`}>开始十分钟复习</Link>
          <Link className="button button--secondary" to={`/courses/${courseId}`}>返回课程</Link>
        </div>
      </div>
    )
  }

  return (
    <div>
      <PageHeading
        eyebrow="课后两分钟"
        title="记录今天讲了什么"
        description="只选当天页面；最多补充三类课堂信息，不需要重新整理整份课件。"
      />
      <form className="lesson-form" onSubmit={(event) => { event.preventDefault(); saveLesson.mutate() }}>
        <section className="lab-section form-section">
          <div className="step-index">01</div>
          <div className="step-content">
            <h2>选择课程和课件</h2>
            <div className="form-grid">
              <label>课程
                <select value={courseId} onChange={(event) => setCourseId(event.target.value)} required>
                  <option value="">请选择课程</option>
                  {courses.data?.map((course) => <option value={course.id} key={course.id}>{course.title}</option>)}
                </select>
              </label>
              <label>课件 ID
                <input value={documentId} onChange={(event) => setDocumentId(event.target.value)} placeholder="从课程页选择课件可自动带入" required={!initialNotebook} />
              </label>
            </div>
          </div>
        </section>

        <section className="lab-section form-section">
          <div className="step-index">02</div>
          <div className="step-content">
            <h2>圈出今天的页面</h2>
            {initialNotebook && <div className="notice">本次将使用已导入的 NotebookLM 学习指南作为来源。</div>}
            {document.isPending && <p className="muted-line">正在读取页面…</p>}
            {availablePages.length > 0 ? (
              <div className="page-picker">
                {availablePages.map((page) => (
                  <button
                    className={selectedPages.includes(page.page_number) ? 'is-selected' : ''}
                    type="button"
                    key={page.id}
                    aria-pressed={selectedPages.includes(page.page_number)}
                    onClick={() => togglePage(page.page_number)}
                  >
                    <FileStack aria-hidden="true" />
                    <span>第 {page.page_number} 页</span>
                  </button>
                ))}
              </div>
            ) : (
              <label>页码范围
                <input value={manualPages} onChange={(event) => setManualPages(event.target.value)} placeholder="例如：12-18, 21" required={!initialNotebook} disabled={Boolean(initialNotebook)} />
                <small>可输入单页、逗号或连续范围。</small>
              </label>
            )}
            {finalPages.length > 0 && <p className="selection-summary">已选 {finalPages.length} 页：{finalPages.join('、')}</p>}
          </div>
        </section>

        <section className="lab-section form-section">
          <div className="step-index">03</div>
          <div className="step-content">
            <h2>补上只有课堂里才知道的内容</h2>
            <div className="notes-grid">
              <label><span>老师强调</span><textarea rows={4} value={notes.teacher_emphasis} onChange={(event) => updateNote('teacher_emphasis', event.target.value)} placeholder="反复提醒、容易考错、口头补充…" /></label>
              <label><span>实践内容</span><textarea rows={4} value={notes.practical_content} onChange={(event) => updateNote('practical_content', event.target.value)} placeholder="实验、波形、工艺操作或例题…" /></label>
              <label><span>个人疑问</span><textarea rows={4} value={notes.personal_questions} onChange={(event) => updateNote('personal_questions', event.target.value)} placeholder="当时没想通的地方…" /></label>
            </div>
          </div>
        </section>

        {saveLesson.isError && <div className="notice notice--error">{savedLessonId ? '课堂记录已保存在本机，题目生成未完成；可直接重试，不会重复建课。' : '课堂记录未能保存，请检查本地服务后重试。'}</div>}
        <div className="lesson-submit">
          <div><Sparkles aria-hidden="true" /><span>仅发送所选页面与上述补充</span></div>
          <button className="button button--primary" type="submit" disabled={!courseId || (!initialNotebook && (!documentId || finalPages.length === 0)) || saveLesson.isPending}>
            {saveLesson.isPending ? '正在保存并生成…' : savedLessonId ? '重新生成题目' : '保存并生成复习题'}
          </button>
        </div>
      </form>
    </div>
  )
}
