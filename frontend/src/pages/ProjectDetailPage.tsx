import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Save, Trash2 } from 'lucide-react'
import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { api, type ReviewProjectInput } from '../api/client'
import { ErrorState, LoadingState, PageHeading } from '../components/Ui'
import { AnalysisPage } from './project/AnalysisPage'
import { KeyPointsPage } from './project/KeyPointsPage'
import { MaterialsPage } from './project/MaterialsPage'

const tabs = [
  { label: '概览', number: '01' },
  { label: '资料', number: '02' },
  { label: '分析', number: '03' },
  { label: '重点', number: '04' },
  { label: '复习', number: '05' },
  { label: '掌握情况', number: '06' },
]

export function ProjectDetailPage() {
  const { projectId = '' } = useParams()
  const tabStorageKey = `shiyao:project:${projectId}:active-tab`
  const runStorageKey = `shiyao:project:${projectId}:active-run`
  const [activeTab, setActiveTab] = useState(() => {
    const saved = sessionStorage.getItem(tabStorageKey)
    return tabs.some((tab) => tab.label === saved) ? saved! : '概览'
  })
  const [draft, setDraft] = useState<ReviewProjectInput | null>(null)
  const [selectedBlockIds, setSelectedBlockIds] = useState<string[]>([])
  const [activeRunId, setActiveRunId] = useState<number | null>(() => {
    const saved = Number(sessionStorage.getItem(runStorageKey))
    return Number.isInteger(saved) && saved > 0 ? saved : null
  })
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
  useEffect(() => { sessionStorage.setItem(tabStorageKey, activeTab) }, [activeTab, tabStorageKey])
  useEffect(() => {
    if (activeRunId) sessionStorage.setItem(runStorageKey, String(activeRunId))
    else sessionStorage.removeItem(runStorageKey)
  }, [activeRunId, runStorageKey])

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
            <div className="danger-zone"><div><strong>删除项目</strong><p>将同时删除项目资料、解析内容、分析任务、候选重点与正式重点，且无法撤销。</p></div><button className="button button--danger" type="button" onClick={() => window.confirm('确认删除这个复习项目及全部关联数据？') && deleteProject.mutate()}><Trash2 /> 删除</button></div>
          </form>
        )}
        {activeTab === '资料' && <MaterialsPage projectId={projectId} selectedBlockIds={selectedBlockIds} onSelectedBlockIdsChange={setSelectedBlockIds} />}
        {activeTab === '分析' && <AnalysisPage project={project.data} selectedBlockIds={selectedBlockIds} activeRunId={activeRunId} onActiveRunIdChange={setActiveRunId} />}
        {activeTab === '重点' && <KeyPointsPage projectId={projectId} activeRunId={activeRunId} onOpenSourceBlock={(blockId) => { setSelectedBlockIds((ids) => ids.includes(blockId) ? ids : [...ids, blockId]); setActiveTab('资料') }} />}
        {(activeTab === '复习' || activeTab === '掌握情况') && (
          <div className="step-placeholder"><span>{tabs.find((tab) => tab.label === activeTab)?.number}</span><h2>{activeTab}能力将在下一阶段接通</h2><p>此处现在只展示流程位置，不会伪造处理结果或掌握数据。</p></div>
        )}
      </div>
    </section>
  )
}
