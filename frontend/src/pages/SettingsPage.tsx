import { useMutation, useQuery } from '@tanstack/react-query'
import { CheckCircle2, Download, ExternalLink, KeyRound, Save } from 'lucide-react'
import { FormEvent, useEffect, useState } from 'react'

import { api, downloadBlob, type AISettingsInput } from '../api/client'
import { ErrorState, LoadingState, PageHeading } from '../components/Ui'

export function SettingsPage() {
  const settings = useQuery({ queryKey: ['ai-settings'], queryFn: api.getAISettings })
  const system = useQuery({ queryKey: ['system-info'], queryFn: api.getSystemInfo })
  const [draft, setDraft] = useState<AISettingsInput | null>(null)
  const [apiKey, setApiKey] = useState('')
  const [feedback, setFeedback] = useState('')

  useEffect(() => {
    if (settings.data) setDraft({ ...settings.data })
  }, [settings.data])

  const testConnection = useMutation({
    mutationFn: (payload: AISettingsInput) => api.testAISettings(payload),
    onSuccess: (result) => setFeedback(result.ok ? result.message || '连接校验成功。' : result.message || '连接校验未通过。'),
    onError: (error: Error) => setFeedback(`校验失败：${error.message}`),
  })
  const saveSettings = useMutation({
    mutationFn: (payload: AISettingsInput) => api.saveAISettings(payload),
    onSuccess: () => { setApiKey(''); setFeedback('API 设置已安全保存。') },
    onError: (error: Error) => setFeedback(`保存失败：${error.message}`),
  })

  if (settings.isPending || system.isPending) return <section className="page"><LoadingState label="正在读取设置" /></section>
  if (settings.isError || system.isError || !draft) return <section className="page"><ErrorState title="设置暂时无法读取" description="请确认本机服务正在运行。" onRetry={() => { void settings.refetch(); void system.refetch() }} /></section>

  function payload(): AISettingsInput { return { ...draft!, api_key: apiKey || undefined } }
  function submit(event: FormEvent) { event.preventDefault(); saveSettings.mutate(payload()) }

  return (
    <section className="page settings-page">
      <PageHeading eyebrow="系统" title="设置" description="只保留标准第三方接口；凭证存放在系统凭证库，不会回显到页面。" />
      <form className="settings-card" onSubmit={submit}>
        <div className="section-heading"><div><p className="eyebrow">AI 接入</p><h2>OpenAI 兼容 API</h2></div><span className={draft.api_key_configured ? 'status-tag is-ok' : 'status-tag'}><KeyRound />{draft.api_key_configured ? '已保存凭证' : '未保存凭证'}</span></div>
        <p className="field-hint">适用于支持标准 <code>/v1</code> 接口的第三方服务。保存前建议先校验连接。</p>
        <div className="form-grid">
          <label className="form-grid--wide">API 地址<input value={draft.base_url} onChange={(event) => setDraft({ ...draft, base_url: event.target.value })} placeholder="https://api.example.com/v1" /></label>
          <label>模型名称<input value={draft.model} onChange={(event) => setDraft({ ...draft, model: event.target.value })} placeholder="请输入服务商提供的模型 ID" /></label>
          <label>API Key<input type="password" autoComplete="new-password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder={draft.api_key_configured ? '留空则保留现有凭证' : '输入服务商提供的密钥'} /></label>
        </div>
        <label className="check-row"><input type="checkbox" checked={draft.vision_enabled} onChange={(event) => setDraft({ ...draft, vision_enabled: event.target.checked })} /><span><strong>允许视觉理解</strong><small>处理含图表或扫描页的资料时使用。</small></span></label>
        {feedback && <p className={feedback.includes('失败') || feedback.includes('未通过') ? 'form-error' : 'form-success'} role="status"><CheckCircle2 /> {feedback}</p>}
        <footer className="form-actions"><button className="button button--secondary" type="button" disabled={testConnection.isPending} onClick={() => testConnection.mutate(payload())}>{testConnection.isPending ? '正在校验…' : '校验连接'}</button><button className="button button--primary" type="submit" disabled={saveSettings.isPending}><Save /> {saveSettings.isPending ? '正在保存…' : '保存设置'}</button></footer>
      </form>

      <section className="settings-card">
        <div className="section-heading"><div><p className="eyebrow">本机数据</p><h2>备份与诊断</h2></div><span className="status-tag">v{system.data.version}</span></div>
        <dl className="path-list"><div><dt>数据目录</dt><dd>{system.data.data_directory}</dd></div><div><dt>日志目录</dt><dd>{system.data.log_directory}</dd></div></dl>
        <div className="form-actions"><button className="button button--secondary" type="button" onClick={() => void api.openSystemPath('data')}><ExternalLink /> 打开数据目录</button><button className="button button--secondary" type="button" onClick={() => void api.exportBackup().then((blob) => downloadBlob(blob, 'shiyao-backup.zip'))}><Download /> 导出备份</button><button className="button button--ghost" type="button" onClick={() => void api.exportDiagnostics().then((blob) => downloadBlob(blob, 'shiyao-diagnostics.zip'))}>导出诊断包</button></div>
      </section>
    </section>
  )
}
