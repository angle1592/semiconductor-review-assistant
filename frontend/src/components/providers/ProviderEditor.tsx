import { ArrowRight, CheckCircle2, KeyRound, Search } from 'lucide-react'
import { useMemo, useState } from 'react'

import { api, ApiError, type ModelProfile, type ProviderProfile, type ProviderProtocol } from '../../api/client'
import { ModelManager } from './ModelManager'
import { ProviderErrorPanel } from './ProviderError'

function resolvePreview(protocol: ProviderProtocol, entered: string) {
  try {
    const url = new URL(entered)
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) return null
    let path = url.pathname.replace(/\/$/, '')
    if (!path.endsWith('/v1')) path += '/v1'
    const base = `${url.origin}${path}`
    return { models: `${base}/models`, inference: `${base}/${protocol === 'anthropic' ? 'messages' : 'chat/completions'}` }
  } catch { return null }
}

export function ProviderEditor({ initial, onEnabled, onCancel }: { initial?: ProviderProfile; onEnabled: (provider: ProviderProfile) => void | Promise<void>; onCancel?: () => void }) {
  const [protocol, setProtocol] = useState<ProviderProtocol>(initial?.protocol ?? 'openai_compatible')
  const [name, setName] = useState(initial?.name ?? '主力服务')
  const [baseUrl, setBaseUrl] = useState(initial?.base_url ?? 'https://api.openai.com/v1')
  const [apiKey, setApiKey] = useState('')
  const [provider, setProvider] = useState<ProviderProfile | undefined>(initial)
  const [models, setModels] = useState<ModelProfile[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [manualModel, setManualModel] = useState('')
  const [error, setError] = useState<unknown>()
  const [busy, setBusy] = useState<'models' | 'probe' | 'enable' | ''>('')
  const [enabled, setEnabled] = useState(false)
  const preview = useMemo(() => resolvePreview(protocol, baseUrl), [protocol, baseUrl])
  const selectedModel = models.find((model) => model.id === selectedId)
  const canEnable = selectedModel?.text_status === 'passed'
    && selectedModel.structured_status === 'passed'
    && selectedModel.vision_status === 'passed'
  let activeStep = 0
  if (preview && (apiKey || initial?.api_key_configured)) activeStep = 2
  if (models.length > 0) activeStep = 3
  if (selectedId) activeStep = 4
  if (canEnable || enabled) activeStep = 5

  async function saveProfile() {
    if (!preview) throw new ApiError('API 地址格式不正确。', 422, 'invalid_provider_url')
    const payload = { name: name.trim(), protocol, base_url: baseUrl, api_key: apiKey || undefined }
    const saved = provider ? await api.updateProvider(provider.id, payload) : await api.createProvider(payload)
    setProvider(saved)
    setApiKey('')
    return saved
  }

  async function fetchModels() {
    setBusy('models'); setError(undefined)
    try {
      const saved = await saveProfile()
      const found = await api.refreshModels(saved.id)
      setModels(found)
      if (found[0]) setSelectedId(found[0].id)
    } catch (caught) { setError(caught) } finally { setBusy('') }
  }

  async function addManual() {
    if (!provider || !manualModel.trim()) return
    try {
      const model = await api.addModel(provider.id, { model_id: manualModel.trim(), display_name: manualModel.trim() })
      setModels((current) => [...current.filter((item) => item.id !== model.id), model])
      setSelectedId(model.id); setManualModel(''); setError(undefined)
    } catch (caught) { setError(caught) }
  }

  async function probe() {
    if (!provider || !selectedId) return
    setBusy('probe'); setError(undefined)
    try {
      const result = await api.probeModel(provider.id, selectedId)
      setModels((current) => current.map((model) => model.id === result.id ? result : model))
    } catch (caught) { setError(caught) } finally { setBusy('') }
  }

  async function enable() {
    if (!provider) return
    setBusy('enable'); setError(undefined)
    try {
      const result = await api.enableProvider(provider.id)
      setProvider(result)
      await onEnabled(result)
      setEnabled(true)
    } catch (caught) { setError(caught) } finally { setBusy('') }
  }

  const steps = ['选择协议', '填写地址与密钥', '获取模型', '选择模型', '校验能力', '启用服务']
  return (
    <section className="provider-editor">
      <aside className="provider-steps" aria-label="服务配置步骤">
        {steps.map((step, index) => <div key={step} className={index <= activeStep ? 'is-reached' : ''}><span>{String(index + 1).padStart(2, '0')}</span><strong>{step}</strong></div>)}
      </aside>
      <div className="provider-ticket">
        <div className="section-heading"><div><p className="eyebrow">第三方 AI</p><h2>{initial ? '编辑服务' : '接入新服务'}</h2></div><span className="status-tag"><KeyRound />密钥不回显</span></div>
        <div className="form-grid">
          <label>服务名称<input value={name} onChange={(event) => setName(event.target.value)} /></label>
          <label>协议<select value={protocol} onChange={(event) => setProtocol(event.target.value as ProviderProtocol)}><option value="openai_compatible">OpenAI 兼容</option><option value="anthropic">Anthropic</option></select></label>
          <label className="form-grid--wide">API 地址<input aria-label="API 地址" aria-invalid={!preview} value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} />{!preview && <small className="field-error">请输入不含查询参数和账号信息的 HTTP(S) 地址。</small>}</label>
          <label className="form-grid--wide">API Key<input type="password" autoComplete="new-password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder={initial?.api_key_configured ? '留空则保留现有密钥' : '输入服务商提供的密钥'} /></label>
        </div>
        {preview && <div className="endpoint-ruler"><span><b>模型列表</b><code>{preview.models}</code></span><span><b>推理请求</b><code>{preview.inference}</code></span></div>}
        <button className="button button--secondary" type="button" disabled={busy === 'models' || !preview} onClick={fetchModels}><Search />{busy === 'models' ? '正在获取…' : '获取模型'}</button>
        {error !== undefined && <ProviderErrorPanel error={error} />}
        {error instanceof ApiError && error.code === 'upstream_endpoint_not_found' && <div className="manual-model"><label>手动模型 ID<input value={manualModel} onChange={(event) => setManualModel(event.target.value)} /></label><button className="button button--secondary" type="button" onClick={addManual}>添加模型</button></div>}
        {models.length > 0 && <ModelManager models={models} selectedId={selectedId} onSelect={setSelectedId} onProbe={probe} probing={busy === 'probe'} />}
        {selectedId && !canEnable && <p className="field-hint">文本、结构化输出和视觉三项能力通过后，才可启用此服务。</p>}
        {selectedId && <button className="button button--primary" type="button" disabled={busy === 'enable' || !canEnable} onClick={enable}>{busy === 'enable' ? '正在启用…' : '启用此服务'} <ArrowRight /></button>}
        {enabled && <p className="form-success" role="status"><CheckCircle2 />服务已启用</p>}
        {onCancel && <button className="button button--ghost" type="button" onClick={onCancel}>取消</button>}
      </div>
    </section>
  )
}
