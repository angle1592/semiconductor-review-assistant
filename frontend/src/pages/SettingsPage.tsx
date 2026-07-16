import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, ExternalLink, Plus } from 'lucide-react'
import { useState } from 'react'

import { api, downloadBlob, type ProviderProfile } from '../api/client'
import { ProviderCardContainer } from '../components/providers/ProviderCardContainer'
import { ProviderEditor } from '../components/providers/ProviderEditor'
import { EmptyState, ErrorState, LoadingState, PageHeading } from '../components/Ui'

export function SettingsPage() {
  const queryClient = useQueryClient()
  const providers = useQuery({ queryKey: ['providers'], queryFn: api.listProviders })
  const system = useQuery({ queryKey: ['system-info'], queryFn: api.getSystemInfo })
  const [editing, setEditing] = useState<ProviderProfile | 'new' | null>(null)
  const [actionError, setActionError] = useState('')
  const exportBackup = useMutation({
    mutationFn: api.exportBackup,
    onSuccess: (blob) => downloadBlob(blob, 'shiyao-backup.zip'),
    onError: (error: Error) => setActionError(`备份导出失败：${error.message}`),
  })
  const exportDiagnostics = useMutation({
    mutationFn: api.exportDiagnostics,
    onSuccess: (blob) => downloadBlob(blob, 'shiyao-diagnostics.zip'),
    onError: (error: Error) => setActionError(`诊断包导出失败：${error.message}`),
  })

  async function providerSaved(provider: ProviderProfile) {
    await queryClient.invalidateQueries({ queryKey: ['providers'] })
    await queryClient.invalidateQueries({ queryKey: ['provider-models', provider.id] })
    setEditing(null)
  }

  if (providers.isPending || system.isPending) return <section className="page"><LoadingState label="正在读取设置" /></section>
  if (providers.isError || system.isError) return <section className="page"><ErrorState title="设置暂时无法读取" description="请确认本机服务正在运行。" onRetry={() => { void providers.refetch(); void system.refetch() }} /></section>

  return (
    <section className="page settings-page">
      <PageHeading
        eyebrow="系统"
        title="设置"
        description="管理多个第三方 AI 服务。密钥只保存在系统凭证库，模型能力由固定测试内容实际校验。"
        actions={<button className="button button--primary" type="button" onClick={() => setEditing('new')}><Plus />新增服务</button>}
      />

      {editing && (
        <section className="settings-card provider-editor-card">
          <ProviderEditor
            initial={editing === 'new' ? undefined : editing}
            onEnabled={providerSaved}
            onCancel={() => setEditing(null)}
          />
        </section>
      )}

      <section className="provider-list" aria-label="第三方 AI 服务">
        {providers.data.length === 0 ? (
          <EmptyState title="还没有第三方服务" description="新增服务并完成模型能力校验后，即可用于资料提取。" actionLabel="新增服务" onAction={() => setEditing('new')} />
        ) : providers.data.map((provider) => (
          <ProviderCardContainer key={provider.id} provider={provider} onEdit={() => setEditing(provider)} />
        ))}
      </section>

      <section className="settings-card">
        <div className="section-heading"><div><p className="eyebrow">本机数据</p><h2>备份与诊断</h2></div><span className="status-tag">v{system.data.version}</span></div>
        <dl className="path-list"><div><dt>数据目录</dt><dd>{system.data.data_directory}</dd></div><div><dt>日志目录</dt><dd>{system.data.log_directory}</dd></div></dl>
        {actionError && <p className="form-error" role="alert">{actionError}</p>}
        <div className="form-actions">
          <button className="button button--secondary" type="button" onClick={() => void api.openSystemPath('data').catch((error: Error) => setActionError(`目录打开失败：${error.message}`))}><ExternalLink />打开数据目录</button>
          <button className="button button--secondary" type="button" disabled={exportBackup.isPending} onClick={() => exportBackup.mutate()}><Download />{exportBackup.isPending ? '正在导出…' : '导出备份'}</button>
          <button className="button button--ghost" type="button" disabled={exportDiagnostics.isPending} onClick={() => exportDiagnostics.mutate()}>{exportDiagnostics.isPending ? '正在导出…' : '导出诊断包'}</button>
        </div>
      </section>
    </section>
  )
}
