import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BookOpen, Play, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'

import { keyPointKeys, keypointsApi } from '../../api/keypoints'
import { studyApi, studyKeys, type Artifact, type ArtifactKind } from '../../api/study'
import { ArtifactGenerator } from '../../components/ArtifactGenerator'
import { EmptyState, ErrorState, LoadingState } from '../../components/Ui'
import { StudySessionPage } from './StudySessionPage'

export function ReviewContentPage({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient()
  const [kind, setKind] = useState<ArtifactKind>('outline')
  const [pointIds, setPointIds] = useState<number[]>([])
  const [questionIds, setQuestionIds] = useState<number[]>([])
  const [providerId, setProviderId] = useState('')
  const [modelId, setModelId] = useState('')
  const [prompt, setPrompt] = useState('')
  const [activeArtifactId, setActiveArtifactId] = useState<number | null>(() => Number(sessionStorage.getItem(`shiyao:project:${projectId}:artifact`)) || null)
  const [sessionItem, setSessionItem] = useState<{ artifact?: Artifact; questionId?: number } | null>(null)
  const points = useQuery({ queryKey: keyPointKeys.confirmed(projectId), queryFn: () => keypointsApi.list(projectId) })
  const questions = useQuery({ queryKey: studyKeys.questions(projectId), queryFn: () => studyApi.questions(projectId) })
  const artifacts = useQuery({ queryKey: studyKeys.artifacts(projectId), queryFn: () => studyApi.artifacts(projectId) })
  const active = useQuery({ queryKey: studyKeys.artifact(activeArtifactId ?? 0), queryFn: () => studyApi.artifact(activeArtifactId!), enabled: activeArtifactId !== null, refetchInterval: (query) => query.state.data && ['queued', 'running'].includes(query.state.data.status) ? 1500 : false })
  useEffect(() => { if (activeArtifactId) sessionStorage.setItem(`shiyao:project:${projectId}:artifact`, String(activeArtifactId)); else sessionStorage.removeItem(`shiyao:project:${projectId}:artifact`) }, [activeArtifactId, projectId])
  const generate = useMutation({ mutationFn: () => studyApi.generate(projectId, { kind, keypoint_ids: pointIds, source_question_ids: questionIds, provider_id: providerId, model_profile_id: modelId, run_override: prompt }), onSuccess: (artifact) => { setActiveArtifactId(artifact.id); void queryClient.invalidateQueries({ queryKey: studyKeys.artifacts(projectId) }) } })
  const remove = useMutation({ mutationFn: (artifact: Artifact) => studyApi.removeArtifact(artifact.id), onSuccess: (_, artifact) => { if (activeArtifactId === artifact.id) setActiveArtifactId(null); void queryClient.invalidateQueries({ queryKey: studyKeys.artifacts(projectId) }) } })
  if (sessionItem) return <StudySessionPage projectId={projectId} artifact={sessionItem.artifact} sourceQuestion={questions.data?.find((item) => item.id === sessionItem.questionId)} onClose={() => setSessionItem(null)} />
  if (points.isPending || questions.isPending || artifacts.isPending) return <LoadingState label="正在整理复习内容" />
  if (points.isError || questions.isError || artifacts.isError) return <ErrorState title="复习内容未能加载" description="请检查本机服务后重试。" onRetry={() => { void points.refetch(); void questions.refetch(); void artifacts.refetch() }} />
  return <div className="review-content"><div className="workspace-intro"><div><p className="eyebrow">步骤 05 · 复习</p><h2>需要时再开始，不安排每日任务</h2><p>选择提纲、记忆卡、原题或 AI 题目。这里不设置日程、连续天数或自动下一场。</p></div><span className="binding-status">按需复习</span></div><ArtifactGenerator kind={kind} onKindChange={setKind} points={points.data} questions={questions.data} selectedPointIds={pointIds} selectedQuestionIds={questionIds} onPointIdsChange={setPointIds} onQuestionIdsChange={setQuestionIds} providerId={providerId} modelId={modelId} onProviderChange={setProviderId} onModelChange={setModelId} prompt={prompt} onPromptChange={setPrompt} pending={generate.isPending} onGenerate={() => generate.mutate()} />{generate.isError && <p className="form-error" role="alert">生成任务未能创建，请核对选择和 AI 接入。</p>}{active.data && ['queued', 'running'].includes(active.data.status) && <div className="analysis-queued" role="status"><BookOpen /><div><strong>生成任务正在后台运行</strong><p>刷新或离开页面后仍会继续；返回时自动恢复进度。</p></div></div>}{active.data?.status === 'failed' && <p className="form-error">生成失败：{active.data.error_detail || active.data.public_error_code}</p>}<section className="review-library"><div className="section-heading"><div><p className="eyebrow">内容库</p><h2>已生成内容与原题</h2></div></div>{!artifacts.data.length && !questions.data.length && <EmptyState title="还没有可复习内容" description="先确认重点，再按上方选择一种形式生成；分析提取出的原题也会保留在这里。" />}{questions.data.map((question) => <article className="review-library-row" key={`q-${question.id}`}><div><small>原题 · 保留来源</small><h3>{question.question_text}</h3></div><button className="button button--secondary" type="button" onClick={() => setSessionItem({ questionId: question.id })}><Play /> 开始作答</button></article>)}{artifacts.data.map((artifact) => <article className="review-library-row" key={artifact.id}><div><small>{artifact.kind} · {artifact.status}{artifact.cache_status ? ` · 缓存 ${artifact.cache_status}` : ''}</small><h3>{artifact.payload.outline?.title || `生成内容 #${artifact.id}`}</h3><p>依据 {artifact.keypoint_ids.length} 条已确认重点{artifact.source_question_ids.length ? `、${artifact.source_question_ids.length} 道原题` : ''}</p></div><div className="candidate-toolbar"><button className="button button--secondary" type="button" disabled={artifact.status !== 'succeeded'} onClick={() => setSessionItem({ artifact })}><Play /> 开始复习</button><button className="icon-button" type="button" aria-label={`删除生成内容 ${artifact.id}`} onClick={() => remove.mutate(artifact)}><Trash2 /></button></div></article>)}</section></div>
}
