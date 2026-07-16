import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { masteryApi, masteryKeys, type MasteryLevel, type TargetType } from '../../api/mastery'
import { MasteryControl } from '../../components/MasteryControl'
import { EmptyState, ErrorState, LoadingState } from '../../components/Ui'

const levelLabels: Record<MasteryLevel, string> = { unrated: '未评级', learning: '学习中', familiar: '已熟悉', mastered: '已掌握' }

export function MasteryPage({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient()
  const [level, setLevel] = useState('')
  const [type, setType] = useState('')
  const summary = useQuery({ queryKey: masteryKeys.summary(projectId), queryFn: () => masteryApi.summary(projectId) })
  const records = useQuery({ queryKey: [...masteryKeys.records(projectId), level, type], queryFn: () => masteryApi.records(projectId, level, type) })
  const rate = useMutation({ mutationFn: ({ targetType, targetId, value }: { targetType: TargetType; targetId: number; value: MasteryLevel }) => masteryApi.rate(projectId, targetType, targetId, value), onSuccess: () => { void queryClient.invalidateQueries({ queryKey: masteryKeys.records(projectId) }); void queryClient.invalidateQueries({ queryKey: masteryKeys.summary(projectId) }) } })
  if (summary.isPending || records.isPending) return <LoadingState label="正在汇总掌握情况" />
  if (summary.isError || records.isError) return <ErrorState title="掌握情况未能加载" description="请检查本机服务后重试。" onRetry={() => { void summary.refetch(); void records.refetch() }} />
  return <div className="project-mastery"><div className="workspace-intro"><div><p className="eyebrow">步骤 06 · 掌握情况</p><h2>只记录你明确给出的判断</h2><p>计数来自主动复习和手动评级，不推算考试日、到期日或连续学习。</p></div></div><div className="mastery-summary">{(['learning', 'familiar', 'mastered'] as MasteryLevel[]).map((item) => <article key={item}><span>{levelLabels[item]}</span><strong>{summary.data.by_level[item] ?? 0}</strong></article>)}</div><div className="mastery-filters"><label>掌握程度<select aria-label="按掌握程度筛选" value={level} onChange={(event) => setLevel(event.target.value)}><option value="">全部</option>{Object.entries(levelLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>内容类型<select aria-label="按内容类型筛选" value={type} onChange={(event) => setType(event.target.value)}><option value="">全部</option><option value="keypoint">重点</option><option value="source_question">原题</option><option value="artifact">生成内容</option></select></label></div>{!records.data.length && <EmptyState title="还没有掌握记录" description="开始一次按需复习并选择掌握程度后，这里会出现记录。" />}{records.data.map((record) => <article className="mastery-row" key={record.id}><div><small>{record.target_type} #{record.target_id}</small><strong>{levelLabels[record.level]}</strong>{record.last_attempt_at && <time>{new Date(record.last_attempt_at).toLocaleString('zh-CN')}</time>}</div><MasteryControl value={record.level} disabled={rate.isPending} onChange={(value) => rate.mutate({ targetType: record.target_type, targetId: record.target_id, value })} /></article>)}</div>
}
