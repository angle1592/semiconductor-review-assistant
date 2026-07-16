import { useMutation } from '@tanstack/react-query'
import { ArrowRight, CheckCircle2, ShieldCheck } from 'lucide-react'
import { FormEvent, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { api, type AISettingsInput } from '../api/client'

export function SetupPage() {
  const navigate = useNavigate()
  const [draft, setDraft] = useState<AISettingsInput>({ provider: 'openai_compatible', base_url: 'https://api.openai.com/v1', model: '', vision_enabled: true })
  const [apiKey, setApiKey] = useState('')
  const [message, setMessage] = useState('')
  const configure = useMutation({
    mutationFn: async () => {
      const payload = { ...draft, api_key: apiKey || undefined }
      const tested = await api.testAISettings(payload)
      if (!tested.ok) throw new Error(tested.message || '连接校验未通过')
      await api.saveAISettings(payload)
      await api.completeSetup()
    },
    onSuccess: () => { setApiKey(''); navigate('/projects') },
    onError: (error: Error) => setMessage(`设置未完成：${error.message}`),
  })

  function submit(event: FormEvent) {
    event.preventDefault()
    setMessage('')
    configure.mutate()
  }

  return (
    <section className="setup-page">
      <div className="setup-intro">
        <span className="brand-bookmark brand-bookmark--large" aria-hidden="true"><b>拾</b><b>要</b></span>
        <p className="eyebrow">首次设置</p>
        <h1>连接你的第三方 AI</h1>
        <p>拾要需要 AI 从 PPT、Word 等资料中识别重点。我们会先实际校验连接，成功后才保存并继续。</p>
        <ul><li><ShieldCheck /> API Key 写入系统凭证库</li><li><CheckCircle2 /> 页面不会回显已保存的密钥</li></ul>
      </div>
      <form className="setup-form" onSubmit={submit}>
        <div><span className="step-label">01 / 接口</span><h2>OpenAI 兼容 API</h2><p>填写服务商给出的接口地址、模型 ID 和密钥。</p></div>
        <label>API 地址<input required value={draft.base_url} onChange={(event) => setDraft({ ...draft, base_url: event.target.value })} placeholder="https://api.example.com/v1" /></label>
        <label>模型名称<input required value={draft.model} onChange={(event) => setDraft({ ...draft, model: event.target.value })} placeholder="例如：provider-model-id" /></label>
        <label>API Key<input required type="password" autoComplete="new-password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} /></label>
        <label className="check-row"><input type="checkbox" checked={draft.vision_enabled} onChange={(event) => setDraft({ ...draft, vision_enabled: event.target.checked })} /><span><strong>允许视觉理解</strong><small>建议开启，用于识别资料里的图表和扫描页。</small></span></label>
        {message && <p className="form-error" role="alert">{message}</p>}
        <button className="button button--primary setup-submit" disabled={configure.isPending} type="submit">{configure.isPending ? '正在校验连接…' : '测试、保存并继续'} <ArrowRight /></button>
      </form>
    </section>
  )
}
