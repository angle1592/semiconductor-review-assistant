import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Bot, ChevronDown, KeyRound, ShieldCheck } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import { api, type AISettings } from '../api/client'


type SetupForm = AISettings & { api_key: string }

const initialForm: SetupForm = {
  provider: 'openai_compatible',
  base_url: 'https://api.openai.com/v1',
  model: '',
  api_key: '',
  vision_enabled: true,
}


export function SetupPage() {
  const navigate = useNavigate()
  const [form, setForm] = useState(initialForm)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const save = useMutation({
    mutationFn: api.saveAISettings,
    onSuccess: () => navigate('/', { replace: true }),
  })

  function update<K extends keyof SetupForm>(key: K, value: SetupForm[K]) {
    setForm((current) => ({ ...current, [key]: value }))
  }

  return (
    <div className="setup-page">
      <div className="setup-mark"><Bot aria-hidden="true" /></div>
      <p className="eyebrow">首次使用 · 约 1 分钟</p>
      <h1>先连接你的 AI 服务</h1>
      <p className="setup-intro">每位使用者填写自己的服务地址、模型和密钥。密钥只进入 Windows 凭据存储，不写入课程数据库或备份。</p>

      <form className="settings-form setup-form" onSubmit={(event) => { event.preventDefault(); save.mutate(form) }}>
        {form.provider === 'openai_compatible' ? (
          <div className="form-grid">
            <label>服务地址
              <input value={form.base_url} onChange={(event) => update('base_url', event.target.value)} required />
            </label>
            <label>模型名称
              <input value={form.model} onChange={(event) => update('model', event.target.value)} placeholder="例如 gpt-4.1-mini" required />
            </label>
            <label className="form-span">API Key
              <div className="secret-input"><KeyRound aria-hidden="true" /><input type="password" value={form.api_key} onChange={(event) => update('api_key', event.target.value)} autoComplete="off" required /></div>
            </label>
            <label className="check-row form-span">
              <input type="checkbox" checked={form.vision_enabled ?? true} onChange={(event) => update('vision_enabled', event.target.checked)} />
              <span><strong>允许处理所选课件页面图片</strong><small>只有你在课次中选择的页面会发送给当前服务。</small></span>
            </label>
          </div>
        ) : (
          <div className="advanced-provider">
            <Bot aria-hidden="true" />
            <div><h2>使用本机 Codex 登录</h2><p>高级选项。复用这台电脑已有的 Codex 认证，不复制凭据。</p></div>
            <label>模型名称<input value={form.model} onChange={(event) => update('model', event.target.value)} placeholder="gpt-5.2-codex" required /></label>
          </div>
        )}

        {save.isError && <div className="notice notice--error" role="alert">设置未保存，请检查本地服务后重试。</div>}
        <div className="setup-actions">
          <button className="button button--primary button--large" type="submit" disabled={save.isPending}>{save.isPending ? '正在保存…' : '保存并进入复习台'}</button>
          <button className="button button--ghost" type="button" onClick={() => setShowAdvanced((value) => !value)}><ChevronDown aria-hidden="true" />高级：使用 Codex</button>
        </div>
        {showAdvanced && (
          <button className="advanced-choice" type="button" onClick={() => update('provider', form.provider === 'codex' ? 'openai_compatible' : 'codex')}>
            <strong>使用本机 Codex 登录</strong><span>{form.provider === 'codex' ? '切回 OpenAI 兼容 API' : '选择高级后端'}</span>
          </button>
        )}
      </form>

      <div className="privacy-strip"><ShieldCheck aria-hidden="true" /><p><strong>正式学习数据只保存在本机。</strong> 以后可在设置页随时更换后端、导出备份或诊断包。</p></div>
    </div>
  )
}
