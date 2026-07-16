import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Save, Trash2 } from 'lucide-react'
import { FormEvent, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { api, type ReviewProjectInput } from '../api/client'
import { ErrorState, LoadingState, PageHeading } from '../components/Ui'

const tabs = [
  { label: '概览', number: '01' },
  { label: '资料', number: '02' },
  { label: '重点', number: '03' },
  { label: '复习', number: '04' },
  { label: '掌握情况', number: '05' },
]

export function ProjectDetailPage() {
  const { projectId = '' } = useParams()
  const [activeTab, setActiveTab] = useState('概览')
  const [draft, setDraft] = useState<ReviewProjectInput | null>(null)
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const project = useQuery({ queryKey: ['project', projectId], queryFn: () => api.getProject(projectId), enabled: Boolean(projectId) })
  const updateProject = useMutation({
    mutationFn: (payload: ReviewProjectInput) => api.updateProject(projectId, payload),
    onSuccess: (saved) => {
      queryClient.setQueryData(['project', projectId], saved)
      void queryClient.invalidateQueries({ queryKey: ['projects'] })
    },
  })
  const deleteProject = useMutation({
    mutationFn: () => api.deleteProject(projectId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['projects'] })
      navigate('/projects')
    },
  })

  useEffect(() => {
    if (project.data) setDraft({ name: project.data.name, description: project.data.description, importance_prompt: project.data.importance_prompt })
  }, [project.data])

  if (project.isPending) return <section className="page"><LoadingState label="正在打开项目" /></section>
  if (project.isError || !project.data) return <section className="page"><ErrorState title="项目无法打开" description="项目可能已被删除，或本机服务暂时不可用。" onRetry={() => void project.refetch()} /></section>

  function save(event: FormEvent) {
    event.preventDefault()
    if (draft?.name.trim()) updateProject.mutate({ ...draft, name: draft.name.trim() })
  }

  return (
    <section className="page project-workspace">
      <Link to="/projects" className="back-link"><ArrowLeft /> 返回项目索引</Link>
      <PageHeading eyebrow="复习项目" title={project.data.name} description={project.data.description || '尚未填写项目说明'} />
      <div className="workspace-tabs" role="tablist" aria-label="项目工作步骤">
        {tabs.map((tab) => <button key={tab.label} id={`project-tab-${tab.number}`} type="button" role="tab" aria-controls="project-tab-panel" aria-label={tab.label} aria-selected={activeTab === tab.label} onClick={() => setActiveTab(tab.label)}><span aria-hidden="true">{tab.number}</span>{tab.label}</button>)}
      </div>

      <div id="project-tab-panel" className="workspace-panel" role="tabpanel" aria-labelledby={`project-tab-${tabs.find((tab) => tab.label === activeTab)?.number}`}>
        {activeTab === '概览' && draft && (
          <form className="project-form" onSubmit={save}>
            <div className="section-heading"><div><p className="eyebrow">项目定义</p><h2>这次复习要解决什么</h2></div><button className="button button--secondary" type="submit" disabled={updateProject.isPending}><Save /> 保存修改</button></div>
            <label>项目名称<input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></label>
            <label>项目说明<textarea value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} /></label>
            <label>什么内容最重要<textarea value={draft.importance_prompt} onChange={(event) => setDraft({ ...draft, importance_prompt: event.target.value })} placeholder="可以由你直接说明，也可以作为 AI 判断重点的提示词。" /></label>
            {updateProject.isSuccess && <p className="form-success" role="status">项目设置已保存。</p>}
            <div className="danger-zone"><div><strong>删除项目</strong><p>当前阶段只会删除项目定义。后续资料也会随项目一起删除。</p></div><button className="button button--danger" type="button" onClick={() => window.confirm('确认删除这个复习项目？') && deleteProject.mutate()}><Trash2 /> 删除</button></div>
          </form>
        )}
        {activeTab !== '概览' && (
          <div className="step-placeholder"><span>{tabs.find((tab) => tab.label === activeTab)?.number}</span><h2>{activeTab}能力将在下一阶段接通</h2><p>此处现在只展示流程位置，不会伪造处理结果或掌握数据。</p></div>
        )}
      </div>
    </section>
  )
}
