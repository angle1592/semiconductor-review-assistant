import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowUpRight, FolderPlus, X } from 'lucide-react'
import { FormEvent, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { api, type ReviewProjectInput } from '../api/client'
import { EmptyState, ErrorState, LoadingState, PageHeading } from '../components/Ui'

const emptyProject: ReviewProjectInput = { name: '', description: '', importance_prompt: '' }

export function ProjectsPage() {
  const [creating, setCreating] = useState(false)
  const [draft, setDraft] = useState(emptyProject)
  const projects = useQuery({ queryKey: ['projects'], queryFn: api.listProjects, retry: false })
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const createProject = useMutation({
    mutationFn: api.createProject,
    onSuccess: (project) => {
      queryClient.setQueryData(['project', project.id], project)
      void queryClient.invalidateQueries({ queryKey: ['projects'] })
      setCreating(false)
      setDraft(emptyProject)
      navigate(`/projects/${project.id}`)
    },
  })

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!draft.name.trim()) return
    createProject.mutate({ ...draft, name: draft.name.trim() })
  }

  return (
    <section className="page">
      <PageHeading
        eyebrow="资料索引"
        title="复习项目"
        description="每个项目对应一次明确的总复习目标，以及一套由你决定的重点标准。"
        actions={<button className="button button--primary" type="button" onClick={() => setCreating(true)}><FolderPlus /> 新建复习项目</button>}
      />

      {projects.isPending && <LoadingState label="正在读取项目" />}
      {projects.isError && <ErrorState title="项目暂时无法读取" description="请确认本机服务正在运行，然后重试。" onRetry={() => void projects.refetch()} />}
      {projects.data?.length === 0 && <EmptyState title="还没有复习项目" description="点击页面右上角的新建按钮，写下这次要复习什么，以及你认为哪些内容最重要。" />}
      {projects.data && projects.data.length > 0 && (
        <div className="project-index">
          {projects.data.map((project, index) => (
            <Link to={`/projects/${project.id}`} key={project.id} className="project-row">
              <span className="project-order">{String(index + 1).padStart(2, '0')}</span>
              <span>
                <strong>{project.name}</strong>
                <small>{project.description || '尚未填写项目说明'}</small>
              </span>
              <time dateTime={project.updated_at}>{new Date(project.updated_at).toLocaleDateString('zh-CN')}</time>
              <ArrowUpRight aria-hidden="true" />
            </Link>
          ))}
        </div>
      )}

      {creating && (
        <div className="dialog-backdrop" role="presentation">
          <section className="dialog" role="dialog" aria-modal="true" aria-labelledby="create-project-title">
            <header>
              <div><p className="eyebrow">新索引</p><h2 id="create-project-title">建立复习项目</h2></div>
              <button className="icon-button" type="button" aria-label="关闭" onClick={() => setCreating(false)}><X /></button>
            </header>
            <form onSubmit={submit}>
              <label>项目名称<input autoFocus required value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} placeholder="例如：期末总复习" /></label>
              <label>项目说明<textarea value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} placeholder="范围、目标或时间安排" /></label>
              <label>什么内容最重要<textarea value={draft.importance_prompt} onChange={(event) => setDraft({ ...draft, importance_prompt: event.target.value })} placeholder="例如：优先公式、易错点与老师反复强调的内容" /></label>
              {createProject.isError && <p className="form-error" role="alert">项目创建失败，请检查输入后重试。</p>}
              <footer><button className="button button--ghost" type="button" onClick={() => setCreating(false)}>取消</button><button className="button button--primary" disabled={createProject.isPending} type="submit">{createProject.isPending ? '正在创建…' : '创建项目'}</button></footer>
            </form>
          </section>
        </div>
      )}
    </section>
  )
}
