import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowDown, ArrowUp, Check, Edit3, Plus, Save, Trash2, X } from 'lucide-react'
import { useMemo, useState, type FormEvent } from 'react'

import { type Candidate, type Importance, type KeyPoint, keyPointKeys, keypointsApi } from '../../api/keypoints'
import { KeyPointCandidateCard } from '../../components/KeyPointCandidateCard'
import { EmptyState, ErrorState, LoadingState } from '../../components/Ui'

const groups: { key: Importance; label: string; note: string }[] = [
  { key: 'core', label: '核心', note: '必须掌握，直接影响主干理解' },
  { key: 'important', label: '重要', note: '常考、易错或连接多个知识点' },
  { key: 'supplementary', label: '补充', note: '用于完善边界与例外' },
]

const emptyDraft = { title: '', explanation: '', importance: 'important' as Importance }

export function KeyPointsPage({ projectId, activeRunId, onOpenSourceBlock }: { projectId: string; activeRunId: number | null; onOpenSourceBlock: (blockId: string) => void }) {
  const queryClient = useQueryClient()
  const [selected, setSelected] = useState<number[]>([])
  const [notice, setNotice] = useState('')
  const [adding, setAdding] = useState(false)
  const [draft, setDraft] = useState(emptyDraft)
  const [editingPoint, setEditingPoint] = useState<KeyPoint | null>(null)
  const [editDraft, setEditDraft] = useState(emptyDraft)
  const candidates = useQuery({ queryKey: keyPointKeys.candidates(activeRunId ?? 0), queryFn: () => keypointsApi.candidates(activeRunId!), enabled: activeRunId !== null })
  const keypoints = useQuery({ queryKey: keyPointKeys.confirmed(projectId), queryFn: () => keypointsApi.list(projectId) })
  const updateCandidate = useMutation({
    mutationFn: ({ id, value }: { id: number; value: Pick<Candidate, 'title' | 'explanation' | 'importance' | 'rationale'> }) => keypointsApi.updateCandidate(id, value),
    onSuccess: (saved) => queryClient.setQueryData<Candidate[]>(keyPointKeys.candidates(saved.run_id), (old) => old?.map((item) => item.id === saved.id ? saved : item)),
  })
  const bulk = useMutation({
    mutationFn: ({ confirmIds, rejectIds }: { confirmIds: number[]; rejectIds: number[] }) => keypointsApi.bulkAction(confirmIds, rejectIds),
    onSuccess: (result) => { setNotice(`已确认 ${result.confirmed} 条，已拒绝 ${result.rejected} 条。`); setSelected([]); void queryClient.invalidateQueries({ queryKey: keyPointKeys.candidates(activeRunId ?? 0) }); void queryClient.invalidateQueries({ queryKey: keyPointKeys.confirmed(projectId) }) },
  })
  const create = useMutation({ mutationFn: () => keypointsApi.create(projectId, { ...draft, source_block_ids: [], evidence_quotes: [] }), onSuccess: () => { setDraft(emptyDraft); setAdding(false); setNotice('已新增 1 条手工重点。'); void queryClient.invalidateQueries({ queryKey: keyPointKeys.confirmed(projectId) }) } })
  const remove = useMutation({ mutationFn: (point: KeyPoint) => keypointsApi.remove(point.id), onSuccess: () => { setNotice('重点已删除。'); void queryClient.invalidateQueries({ queryKey: keyPointKeys.confirmed(projectId) }) } })
  const update = useMutation({
    mutationFn: () => keypointsApi.update(editingPoint!.id, { ...editDraft, source_block_ids: editingPoint!.source_block_ids, evidence_quotes: editingPoint!.evidence_quotes }),
    onSuccess: (saved) => { queryClient.setQueryData<KeyPoint[]>(keyPointKeys.confirmed(projectId), (old) => old?.map((point) => point.id === saved.id ? saved : point)); setEditingPoint(null); setNotice('重点修改已保存。') },
  })
  const reorder = useMutation({ mutationFn: (orderedIds: number[]) => keypointsApi.reorder(projectId, orderedIds), onSuccess: (saved) => queryClient.setQueryData(keyPointKeys.confirmed(projectId), saved) })
  const pendingCandidates = useMemo(() => candidates.data?.filter((candidate) => candidate.status === 'pending') ?? [], [candidates.data])

  function select(id: number, checked: boolean) { setSelected(checked ? [...new Set([...selected, id])] : selected.filter((item) => item !== id)) }
  function move(point: KeyPoint, delta: number) {
    if (!keypoints.data) return
    const ids = keypoints.data.map((item) => item.id)
    const from = ids.indexOf(point.id)
    const to = from + delta
    if (to < 0 || to >= ids.length) return
    ;[ids[from], ids[to]] = [ids[to], ids[from]]
    reorder.mutate(ids)
  }
  function add(event: FormEvent) { event.preventDefault(); if (draft.title.trim() && draft.explanation.trim()) create.mutate() }
  function beginEdit(point: KeyPoint) { setEditingPoint(point); setEditDraft({ title: point.title, explanation: point.explanation, importance: point.importance }) }

  return (
    <div className="keypoints-workspace">
      <div className="workspace-intro"><div><p className="eyebrow">步骤 04 · 重点</p><h2>把 AI 批注装订成你的复习提纲</h2><p><span>不会自动进入正式复习内容</span>。AI 输出先停留在候选区，确认权始终在你手里。</p></div><span className="binding-status">未确认 {pendingCandidates.length} 条</span></div>
      {notice && <p className="form-success" role="status">{notice}</p>}

      <section className="candidate-section">
        <div className="section-heading"><div><p className="eyebrow">未装订批注</p><h2>AI 候选重点</h2></div><div className="candidate-toolbar"><button className="button button--primary" type="button" disabled={!selected.length || bulk.isPending} onClick={() => bulk.mutate({ confirmIds: selected, rejectIds: [] })}><Check /> 确认所选</button><button className="button button--danger" type="button" disabled={!selected.length || bulk.isPending} onClick={() => bulk.mutate({ confirmIds: [], rejectIds: selected })}><X /> 拒绝所选</button></div></div>
        {!activeRunId && <EmptyState title="还没有分析结果" description="先在“分析”页创建任务。完成后，AI 候选会出现在这里等待你审阅。" />}
        {candidates.isPending && activeRunId && <LoadingState label="正在读取候选重点" />}
        {candidates.isError && <ErrorState title="候选重点未能加载" description="可以重试读取；这不会重复调用第三方 AI。" onRetry={() => void candidates.refetch()} />}
        {activeRunId && candidates.data && !pendingCandidates.length && <EmptyState title="没有待确认候选" description="当前任务没有候选，或所有候选都已经处理。" />}
        {groups.map((group) => {
          const items = pendingCandidates.filter((candidate) => candidate.importance === group.key)
          if (!items.length) return null
          return <div className="candidate-group" key={group.key}><header><span>{group.label}</span><p>{group.note}</p><strong>{items.length}</strong></header>{items.map((candidate) => <KeyPointCandidateCard key={candidate.id} candidate={candidate} selected={selected.includes(candidate.id)} saving={updateCandidate.isPending} onSelectedChange={(checked) => select(candidate.id, checked)} onSave={(value) => updateCandidate.mutate({ id: candidate.id, value })} onOpenSource={onOpenSourceBlock} />)}</div>
        })}
      </section>

      <section className="confirmed-ledger">
        <div className="section-heading"><div><p className="eyebrow">正式提纲</p><h2>已确认重点</h2></div><button className="button button--secondary" type="button" onClick={() => setAdding((value) => !value)}><Plus /> 手工新增</button></div>
        {adding && <form className="manual-keypoint-form" onSubmit={add}><label>重点标题<input value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} /></label><label>解释<textarea value={draft.explanation} onChange={(event) => setDraft({ ...draft, explanation: event.target.value })} /></label><label>重要程度<select value={draft.importance} onChange={(event) => setDraft({ ...draft, importance: event.target.value as Importance })}><option value="core">核心</option><option value="important">重要</option><option value="supplementary">补充</option></select></label><div className="candidate-toolbar"><button className="button button--primary" type="submit" disabled={create.isPending}>保存重点</button><button className="button button--ghost" type="button" onClick={() => setAdding(false)}>取消</button></div></form>}
        {keypoints.isPending && <LoadingState label="正在读取正式提纲" />}
        {keypoints.isError && <ErrorState title="正式提纲未能加载" description="请检查本机服务后重试。" onRetry={() => void keypoints.refetch()} />}
        {keypoints.data && !keypoints.data.length && <EmptyState title="正式提纲还是空的" description="确认 AI 候选，或手工新增第一条重点。" />}
        {keypoints.data?.map((point, index) => <article className="confirmed-row" key={point.id}><span>{String(index + 1).padStart(2, '0')}</span>{editingPoint?.id === point.id ? <form className="confirmed-editor" onSubmit={(event) => { event.preventDefault(); update.mutate() }}><label>重点标题<input value={editDraft.title} onChange={(event) => setEditDraft({ ...editDraft, title: event.target.value })} /></label><label>解释<textarea value={editDraft.explanation} onChange={(event) => setEditDraft({ ...editDraft, explanation: event.target.value })} /></label><label>重要程度<select value={editDraft.importance} onChange={(event) => setEditDraft({ ...editDraft, importance: event.target.value as Importance })}><option value="core">核心</option><option value="important">重要</option><option value="supplementary">补充</option></select></label><div className="candidate-toolbar"><button className="button button--primary" type="submit" disabled={update.isPending}><Save /> 保存修改</button><button className="button button--ghost" type="button" onClick={() => setEditingPoint(null)}>取消</button></div></form> : <div><small>{point.origin === 'ai' ? 'AI 候选 · 已由你确认' : '手工重点'} · {groups.find((group) => group.key === point.importance)?.label}</small><h3>{point.title}</h3><p>{point.explanation}</p></div>}<div className="row-actions"><button className="icon-button" type="button" aria-label={`编辑 ${point.title}`} onClick={() => beginEdit(point)}><Edit3 /></button><button className="icon-button" type="button" aria-label={`上移 ${point.title}`} disabled={index === 0 || reorder.isPending} onClick={() => move(point, -1)}><ArrowUp /></button><button className="icon-button" type="button" aria-label={`下移 ${point.title}`} disabled={index === keypoints.data.length - 1 || reorder.isPending} onClick={() => move(point, 1)}><ArrowDown /></button><button className="icon-button" type="button" aria-label={`删除 ${point.title}`} disabled={remove.isPending} onClick={() => window.confirm('删除这条正式重点？') && remove.mutate(point)}><Trash2 /></button></div></article>)}
      </section>
    </div>
  )
}
