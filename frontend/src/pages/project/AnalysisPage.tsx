import { useMutation, useQuery } from '@tanstack/react-query'
import { AlertTriangle, Bot, CircleDollarSign, Play, ShieldCheck } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { analysisApi, analysisKeys, type AnalysisScope } from '../../api/analysis'
import { api, ApiError, type ReviewProject } from '../../api/client'
import { AnalysisProgress } from '../../components/AnalysisProgress'
import { ErrorState, LoadingState } from '../../components/Ui'

const activeStatuses = new Set(['queued', 'running'])

export function AnalysisPage({ project, selectedBlockIds, activeRunId, onActiveRunIdChange }: { project: ReviewProject; selectedBlockIds: string[]; activeRunId: number | null; onActiveRunIdChange: (id: number | null) => void }) {
  const [scopeMode, setScopeMode] = useState<'selected_blocks' | 'all_sources'>(selectedBlockIds.length ? 'selected_blocks' : 'all_sources')
  const [providerId, setProviderId] = useState('')
  const [modelId, setModelId] = useState('')
  const [runOverride, setRunOverride] = useState('')
  const [confirmedAll, setConfirmedAll] = useState(false)
  const [runId, setRunId] = useState<number | null>(activeRunId)
  const providers = useQuery({ queryKey: ['providers'], queryFn: api.listProviders })
  const enabledProviders = useMemo(() => providers.data?.filter((provider) => provider.enabled) ?? [], [providers.data])
  useEffect(() => { if (!providerId && enabledProviders.length) setProviderId((enabledProviders.find((provider) => provider.is_default) ?? enabledProviders[0]).id) }, [enabledProviders, providerId])
  const models = useQuery({ queryKey: ['provider-models', providerId], queryFn: () => api.listModels(providerId), enabled: Boolean(providerId) })
  useEffect(() => { if (!modelId && models.data?.length) setModelId(models.data.find((model) => model.structured_status === 'passed')?.id ?? models.data[0].id) }, [modelId, models.data])

  const scope: AnalysisScope = useMemo(() => scopeMode === 'all_sources' ? { mode: 'all_sources', block_ids: [] } : { mode: 'selected_blocks', block_ids: selectedBlockIds }, [scopeMode, selectedBlockIds])
  const estimate = useQuery({ queryKey: analysisKeys.estimate(project.id, scope), queryFn: () => analysisApi.estimate(project.id, scope), enabled: scopeMode === 'all_sources' || selectedBlockIds.length > 0 })
  const run = useQuery({ queryKey: analysisKeys.run(runId ?? 0), queryFn: () => analysisApi.get(runId!), enabled: runId !== null, refetchInterval: (query) => query.state.data && activeStatuses.has(query.state.data.status) ? 1500 : false })
  const create = useMutation({ mutationFn: () => analysisApi.create(project.id, { scope, provider_id: providerId, model_profile_id: modelId, run_override: runOverride, parameters: { temperature: 0 }, confirm_large_range: confirmedAll }), onSuccess: (created) => { setRunId(created.run_id); onActiveRunIdChange(created.run_id) } })
  const cancel = useMutation({ mutationFn: () => analysisApi.cancel(runId!), onSuccess: () => void run.refetch() })
  const retry = useMutation({ mutationFn: () => analysisApi.retry(runId!), onSuccess: () => void run.refetch() })
  const selectedModel = models.data?.find((model) => model.id === modelId)
  const modelReady = selectedModel?.text_status === 'passed' && selectedModel.structured_status === 'passed'
  const needsConfirmation = scopeMode === 'all_sources' && Boolean(estimate.data?.exceeds_warning)
  const startDisabled = create.isPending || !providerId || !modelReady || (scopeMode === 'selected_blocks' && !selectedBlockIds.length) || (needsConfirmation && !confirmedAll)
  const createError = create.error instanceof ApiError ? create.error : null

  return (
    <div className="analysis-workspace">
      <div className="workspace-intro"><div><p className="eyebrow">步骤 03 · 分析</p><h2>发出一张可核对的分析工单</h2><p>范围、提示词、服务商和模型都会固化进任务快照。任务在后台运行，离开页面也不会中断。</p></div><span className="binding-status"><ShieldCheck /> AI 结果必须由你确认</span></div>
      <div className="ai-boundary"><Bot /><div><strong>AI 只生成候选重点</strong><p>候选不会自动进入正式复习内容。你可以编辑、拒绝，或批量确认。</p></div></div>
      <div className="analysis-form-grid">
        <section className="analysis-order">
          <div className="section-heading"><div><p className="eyebrow">01 · 范围</p><h2>分析哪些内容</h2></div></div>
          <label className="scope-option"><input type="radio" name="scope" checked={scopeMode === 'selected_blocks'} onChange={() => { setScopeMode('selected_blocks'); setConfirmedAll(false) }} /><span><strong>仅分析已选内容块</strong><small>当前已选 {selectedBlockIds.length} 块；可回到“资料”页调整。</small></span></label>
          <label className="scope-option"><input type="radio" name="scope" aria-label="分析项目内全部资料" checked={scopeMode === 'all_sources'} onChange={() => setScopeMode('all_sources')} /><span><strong>分析项目内全部资料</strong><small>适合总复习，但可能消耗更多时间和第三方额度。</small></span></label>
          {estimate.isPending && <LoadingState label="正在估算范围" />}
          {estimate.data && <div className="analysis-ticket"><span>预计范围</span><strong>{estimate.data.page_count} 页 · {estimate.data.block_count} 个内容块</strong><small>{estimate.data.source_count} 份资料 · 约 {estimate.data.character_count.toLocaleString()} 字 · {estimate.data.image_count} 张图</small></div>}
          {needsConfirmation && <div className="range-warning"><AlertTriangle /><div><strong>范围较大</strong><p>这会增加处理时间和第三方 API 用量。你也可以回到资料页缩小范围。</p><label><input type="checkbox" checked={confirmedAll} onChange={(event) => setConfirmedAll(event.target.checked)} /> 我确认分析全部资料并接受可能的额度消耗</label></div></div>}
        </section>
        <section className="analysis-order">
          <div className="section-heading"><div><p className="eyebrow">02 · 判断标准</p><h2>告诉 AI 什么重要</h2></div></div>
          <div className="prompt-snapshot"><span>项目默认提示词</span><p>{project.importance_prompt || '未设置。AI 将按通用复习标准识别定义、公式、易错点和常考关系。'}</p></div>
          <label>本次补充要求（可选）<textarea value={runOverride} onChange={(event) => setRunOverride(event.target.value)} placeholder="例如：特别关注计算题步骤、老师反复强调的例外。" /></label>
        </section>
        <section className="analysis-order">
          <div className="section-heading"><div><p className="eyebrow">03 · AI 接入</p><h2>选择已校验的模型</h2></div><a className="button button--ghost" href="/settings">管理接入</a></div>
          <label>服务商<select value={providerId} onChange={(event) => { setProviderId(event.target.value); setModelId('') }}><option value="">请选择</option>{enabledProviders.map((provider) => <option key={provider.id} value={provider.id}>{provider.name}</option>)}</select></label>
          <label>模型<select value={modelId} onChange={(event) => setModelId(event.target.value)} disabled={!providerId || models.isPending}><option value="">请选择</option>{models.data?.map((model) => <option key={model.id} value={model.id}>{model.display_name} · {model.structured_status === 'passed' ? '结构化已校验' : '待校验'}</option>)}</select></label>
          {!enabledProviders.length && !providers.isPending && <div className="inline-guidance"><AlertTriangle /><p>没有已启用的第三方服务商。请先在设置中填写 API Key、获取模型并完成校验。</p></div>}
          {selectedModel && !modelReady && <div className="source-warning is-error"><AlertTriangle /><div><strong>这个模型还不能用于分析</strong><p>需要文本与结构化输出校验均通过。请到接入设置执行模型校验。</p><a className="button button--secondary" href="/settings">前往校验</a></div></div>}
        </section>
      </div>
      {createError && <div className="source-warning is-error" role="alert"><AlertTriangle /><div><strong>分析任务未能创建</strong><p>{createError.message}</p>{createError.action === 'select_smaller_range' && <button type="button" className="button button--secondary" onClick={() => { setScopeMode('selected_blocks'); setConfirmedAll(false) }}>改用已选内容块</button>}</div></div>}
      <button className="button button--primary analysis-start" type="button" disabled={startDisabled} onClick={() => create.mutate()}><Play /> 开始后台分析</button>
      {create.isSuccess && <div className="analysis-queued" role="status"><CircleDollarSign /><div><strong>{create.data.message}</strong><p>任务 #{create.data.run_id} · 共 {create.data.batch_count} 批。已完成批次可能命中本机 AI 结果缓存，避免重复请求。</p></div></div>}
      {run.isPending && runId !== null && <LoadingState label="正在读取分析进度" />}
      {run.isError && <ErrorState title="分析进度暂时不可用" description="任务仍可能在后台运行，请重试读取。" onRetry={() => void run.refetch()} />}
      {run.data && <AnalysisProgress run={run.data} pending={cancel.isPending || retry.isPending} onCancel={() => cancel.mutate()} onRetry={() => retry.mutate()} />}
    </div>
  )
}
