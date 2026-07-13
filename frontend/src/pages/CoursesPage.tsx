import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, BookMarked, Plus, Trash2, X } from 'lucide-react'
import { Link } from 'react-router-dom'

import { api, type Course } from '../api/client'
import { EmptyState, ErrorState, LoadingState, PageHeading } from '../components/Ui'

export function CoursesPage() {
  const queryClient = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [notice, setNotice] = useState('')
  const courses = useQuery({ queryKey: ['courses'], queryFn: api.listCourses })
  const createCourse = useMutation({
    mutationFn: api.createCourse,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['courses'] })
      setTitle('')
      setDescription('')
      setShowForm(false)
    },
  })
  const deleteCourse = useMutation({
    mutationFn: async (course: Course) => {
      await api.deleteCourse(course.id)
      return course
    },
    onSuccess: (course) => {
      queryClient.setQueryData<Course[]>(['courses'], (current = []) =>
        current.filter((item) => item.id !== course.id),
      )
      setNotice(`已删除课程“${course.title}”。`)
    },
  })

  function handleCreate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!title.trim()) return
    createCourse.mutate({ title: title.trim(), description: description.trim() })
  }

  function handleDelete(course: Course) {
    const confirmed = window.confirm(
      `确定删除课程“${course.title}”吗？\n\n课程下的课件、课次、题目、答案和复习记录都会一并删除，此操作无法撤销。`,
    )
    if (!confirmed) return
    setNotice('')
    deleteCourse.mutate(course)
  }

  return (
    <div>
      <PageHeading
        eyebrow="课程档案"
        title="课程与课件"
        description="按课程整理页面、课堂记录与复习来源。"
        actions={
          <button className="button button--primary" type="button" onClick={() => setShowForm(true)}>
            <Plus aria-hidden="true" /> 新建课程
          </button>
        }
      />

      {notice && <div className="notice notice--success" role="status">{notice}</div>}
      {deleteCourse.isError && (
        <div className="notice notice--error" role="alert">
          课程删除失败，请确认本地服务正在运行后重试。
        </div>
      )}

      {showForm && (
        <section className="inline-form-panel" aria-label="新建课程">
          <div className="section-heading">
            <div>
              <p className="eyebrow">新增档案</p>
              <h2>这门课叫什么？</h2>
            </div>
            <button className="icon-button" type="button" aria-label="关闭" onClick={() => setShowForm(false)}>
              <X aria-hidden="true" />
            </button>
          </div>
          <form className="form-grid" onSubmit={handleCreate}>
            <label>
              课程名称
              <input value={title} onChange={(event) => setTitle(event.target.value)} required autoFocus />
            </label>
            <label>
              简短说明
              <input
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="例如：本科第六学期 · 周二"
              />
            </label>
            {createCourse.isError && <p className="form-error">课程未保存，请确认本地服务已启动。</p>}
            <div className="form-actions">
              <button className="button button--primary" type="submit" disabled={createCourse.isPending}>
                {createCourse.isPending ? '正在保存…' : '保存课程'}
              </button>
              <button className="button button--ghost" type="button" onClick={() => setShowForm(false)}>取消</button>
            </div>
          </form>
        </section>
      )}

      {courses.isPending && <LoadingState label="正在读取课程档案" />}
      {courses.isError && (
        <ErrorState
          title="课程暂时无法读取"
          description="检查本地服务是否已启动，再重新加载。你的已有数据不会因此被修改。"
          onRetry={() => void courses.refetch()}
        />
      )}
      {courses.data?.length === 0 && !showForm && (
        <EmptyState
          title="还没有课程"
          description="先建立一门课程，再导入今天用到的 PDF 或 PowerPoint。"
          actionLabel="创建第一门课程"
          onAction={() => setShowForm(true)}
        />
      )}
      {courses.data && courses.data.length > 0 && (
        <div className="course-grid">
          {courses.data.map((course) => (
            <article className="course-card" key={course.id}>
              <button
                className="icon-button course-card-delete"
                type="button"
                aria-label={`删除课程 ${course.title}`}
                disabled={deleteCourse.isPending && deleteCourse.variables?.id === course.id}
                onClick={() => handleDelete(course)}
              >
                <Trash2 aria-hidden="true" />
              </button>
              <Link className="course-card-main" to={`/courses/${course.id}`}>
                <span className="course-card-icon"><BookMarked aria-hidden="true" /></span>
                <div>
                  <h2>{course.title}</h2>
                  <p>{course.description || '尚未添加课程说明'}</p>
                </div>
                <span className="course-card-action">打开档案 <ArrowRight aria-hidden="true" /></span>
              </Link>
            </article>
          ))}
        </div>
      )}
    </div>
  )
}
