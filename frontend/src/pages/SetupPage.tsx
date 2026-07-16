import { CheckCircle2, ShieldCheck, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { api } from '../api/client'
import { ProviderEditor } from '../components/providers/ProviderEditor'

export function SetupPage() {
  const navigate = useNavigate()
  const [completionError, setCompletionError] = useState('')

  async function finishSetup() {
    setCompletionError('')
    try {
      await api.completeSetup()
      navigate('/projects')
    } catch (error) {
      const message = error instanceof Error ? error.message : '初始化状态保存失败。'
      setCompletionError(`服务已启用，但初始化未完成：${message}`)
      throw error
    }
  }

  return (
    <section className="setup-page">
      <div className="setup-intro">
        <span className="brand-bookmark brand-bookmark--large" aria-hidden="true"><b>拾</b><b>要</b></span>
        <p className="eyebrow">首次设置</p>
        <h1>连接你的第三方 AI</h1>
        <p>按六个步骤确认接口、模型和实际能力。只有文本、结构化输出与视觉能力全部通过，服务才可启用。</p>
        <ul>
          <li><ShieldCheck /> API Key 写入系统凭证库，页面不回显</li>
          <li><Sparkles /> 校验只发送固定测试内容，不发送你的资料</li>
          <li><CheckCircle2 /> 支持 OpenAI 兼容与 Anthropic 协议</li>
        </ul>
      </div>
      <div className="setup-form">
        {completionError && <p className="form-error" role="alert">{completionError}</p>}
        <ProviderEditor onEnabled={finishSetup} />
      </div>
    </section>
  )
}
