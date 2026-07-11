import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { ArchiveRestore, CheckCircle2, Download, KeyRound, ServerCog, ShieldCheck, Upload } from 'lucide-react'

import { api, type AISettings } from '../api/client'
import { PageHeading } from '../components/Ui'

type SettingsForm = AISettings & { api_key: string }

const initialSettings: SettingsForm = {
  provider: 'openai_compatible',
  base_url: 'https://api.openai.com/v1',
  model: '',
  api_key: '',
  vision_enabled: true,
}

export function SettingsPage() {
  const restoreInput = useRef<HTMLInputElement>(null)
  const [form, setForm] = useState<SettingsForm>(initialSettings)
  const [message, setMessage] = useState('')
  const settings = useQuery({ queryKey: ['ai-settings'], queryFn: api.getAISettings, retry: false })
  const save = useMutation({
    mutationFn: api.saveAISettings,
    onSuccess: () => {
      setMessage('AI 设置已保存。密钥已交给 Windows 凭据存储，数据库不会保存它。')
      setForm((current) => ({ ...current, api_key: '' }))
    },
  })
  const test = useMutation({
    mutationFn: api.testAISettings,
    onSuccess: (result) => setMessage(result.message || (result.ok ? '连接成功，模型能力已更新。' : '连接未通过。')),
  })
  const restore = useMutation({
    mutationFn: api.restoreBackup,
    onSuccess: () => setMessage('备份已校验并恢复。重新打开页面即可读取恢复的数据。'),
  })
  const backup = useMutation({
    mutationFn: api.exportBackup,
    onSuccess: (blob) => {
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `semiconductor-review-${new Date().toISOString().slice(0, 10)}.zip`
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      URL.revokeObjectURL(url)
      setMessage('完整备份已导出；文件中不包含 API Key。')
    },
  })

  useEffect(() => {
    if (!settings.data) return
    setForm((current) => ({ ...current, ...settings.data, api_key: '' }))
  }, [settings.data])

  function update<K extends keyof SettingsForm>(key: K, value: SettingsForm[K]) {
    setForm((current) => ({ ...current, [key]: value }))
  }

  const busy = save.isPending || test.isPending

  return (
    <div>
      <PageHeading eyebrow="本机设置" title="连接与数据边界" description="后端由你手动选择；失败时不会把内容转发给另一项服务。" />
      {message && <div className="notice notice--success" role="status"><CheckCircle2 aria-hidden="true" />{message}</div>}
      {settings.isError && <div className="notice">尚未读到已保存设置。你可以直接填写，保存后由本地服务建立配置。</div>}

      <section className="settings-section lab-section">
        <div className="settings-title">
          <span><ServerCog aria-hidden="true" /></span>
          <div><p className="eyebrow">AI 后端</p><h2>当前生成与评分服务</h2></div>
        </div>
        <form className="settings-form" onSubmit={(event) => { event.preventDefault(); save.mutate(form) }}>
          <fieldset className="provider-choice">
            <legend>选择后端</legend>
            <label className={form.provider === 'openai_compatible' ? 'is-selected' : ''}>
              <input type="radio" name="provider" checked={form.provider === 'openai_compatible'} onChange={() => update('provider', 'openai_compatible')} />
              <span><strong>OpenAI 兼容 API</strong><small>自定义服务地址、模型与 API Key</small></span>
            </label>
            <label className={form.provider === 'codex' ? 'is-selected' : ''}>
              <input type="radio" name="provider" checked={form.provider === 'codex'} onChange={() => update('provider', 'codex')} />
              <span><strong>Codex SDK</strong><small>使用本机已有认证，不复制 Codex 凭据</small></span>
            </label>
          </fieldset>
          <div className="form-grid">
            <label>服务地址
              <input value={form.base_url} onChange={(event) => update('base_url', event.target.value)} disabled={form.provider === 'codex'} required={form.provider === 'openai_compatible'} />
            </label>
            <label>模型名称
              <input value={form.model} onChange={(event) => update('model', event.target.value)} required />
            </label>
            {form.provider === 'openai_compatible' && (
              <label className="form-span">API Key
                <div className="secret-input"><KeyRound aria-hidden="true" /><input type="password" value={form.api_key} onChange={(event) => update('api_key', event.target.value)} autoComplete="off" /></div>
                <small>{settings.data?.api_key_configured ? '已有密钥存于 Windows 凭据存储；留空表示不更换。' : '保存后进入 Windows 凭据存储，不写入 SQLite 或备份。'}</small>
              </label>
            )}
            <label className="check-row form-span">
              <input type="checkbox" checked={form.vision_enabled ?? false} onChange={(event) => update('vision_enabled', event.target.checked)} />
              <span><strong>允许发送所选页面图片</strong><small>只有视觉能力测试通过，图片型课件才会用于出题。</small></span>
            </label>
          </div>
          {(save.isError || test.isError) && <div className="notice notice--error">连接未通过。检查认证、模型名称和视觉能力；系统不会自动切换后端。</div>}
          <div className="form-actions">
            <button className="button button--primary" type="submit" disabled={busy}>{save.isPending ? '正在保存…' : '保存设置'}</button>
            <button className="button button--secondary" type="button" disabled={busy || !form.model} onClick={() => test.mutate(form)}>{test.isPending ? '正在测试…' : '测试连接与能力'}</button>
          </div>
        </form>
      </section>

      <section className="settings-section lab-section">
        <div className="settings-title">
          <span><ArchiveRestore aria-hidden="true" /></span>
          <div><p className="eyebrow">备份与恢复</p><h2>完整带走本机学习记录</h2></div>
        </div>
        <div className="backup-grid">
          <article>
            <Download aria-hidden="true" />
            <div><h3>导出校验备份</h3><p>包含课程、课件索引、问题、答案与排期，不包含任何密钥。</p></div>
            <button className="button button--secondary" type="button" disabled={backup.isPending} onClick={() => backup.mutate()}>{backup.isPending ? '正在打包…' : '下载备份'}</button>
          </article>
          <article>
            <Upload aria-hidden="true" />
            <div><h3>从备份恢复</h3><p>本地服务会先校验文件，再恢复正式数据。</p></div>
            <input ref={restoreInput} type="file" accept=".zip,application/zip" hidden onChange={(event) => { const file = event.target.files?.[0]; if (file) restore.mutate(file); event.target.value = '' }} />
            <button className="button button--secondary" type="button" disabled={restore.isPending} onClick={() => restoreInput.current?.click()}>{restore.isPending ? '正在恢复…' : '选择备份'}</button>
          </article>
        </div>
        {(backup.isError || restore.isError) && <div className="notice notice--error">备份操作未完成。请确认本地服务正在运行，且恢复文件未被修改。</div>}
      </section>

      <div className="privacy-strip"><ShieldCheck aria-hidden="true" /><p><strong>本机数据是唯一权威来源。</strong> 云端只处理你明确选择的页面与课堂补充，不接收整份课件。</p></div>
    </div>
  )
}
