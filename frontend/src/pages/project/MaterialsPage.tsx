import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, Trash2 } from 'lucide-react'
import { useState } from 'react'

import { ApiError } from '../../api/client'
import { sourceKeys, sourcesApi, type SourceDocument } from '../../api/sources'
import { SourcePreview } from '../../components/SourcePreview'
import { SourceUploader } from '../../components/SourceUploader'
import { EmptyState, ErrorState, LoadingState } from '../../components/Ui'

const maxBytes = 100 * 1024 * 1024
const allowed = new Set(['pdf', 'doc', 'docx', 'ppt', 'pptx', 'txt', 'md'])
const statusLabel: Record<string, string> = { pending: '等待解析', parsed: '解析完成', degraded: '解析完成，但有提醒', failed: '解析失败' }

export function MaterialsPage({ projectId, selectedBlockIds, onSelectedBlockIdsChange }: { projectId: string; selectedBlockIds: string[]; onSelectedBlockIdsChange: (ids: string[]) => void }) {
  const queryClient = useQueryClient()
  const [activeSourceId, setActiveSourceId] = useState<number | null>(null)
  const [localError, setLocalError] = useState('')
  const sources = useQuery({ queryKey: sourceKeys.all(projectId), queryFn: () => sourcesApi.list(projectId) })
  const upload = useMutation({
    mutationFn: (file: File) => sourcesApi.upload(projectId, file),
    onSuccess: (result) => { setLocalError(''); setActiveSourceId(result.source_id); void queryClient.invalidateQueries({ queryKey: sourceKeys.all(projectId) }) },
  })
  const remove = useMutation({
    mutationFn: (source: SourceDocument) => sourcesApi.remove(source.id),
    onSuccess: (_, source) => { if (activeSourceId === source.id) setActiveSourceId(null); void queryClient.invalidateQueries({ queryKey: sourceKeys.all(projectId) }) },
  })

  function accept(file: File) {
    const extension = file.name.split('.').pop()?.toLowerCase() ?? ''
    if (!allowed.has(extension)) return setLocalError('无法上传：仅支持 PDF、Word、PPT、TXT 和 Markdown 文件。请重新选择。')
    if (file.size > maxBytes) return setLocalError('文件超过 100 MB。请压缩、拆分资料后重试。')
    upload.mutate(file)
  }

  const apiError = upload.error instanceof ApiError ? upload.error : null
  const activeSource = sources.data?.items.find((source) => source.id === activeSourceId) ?? sources.data?.items[0]

  return (
    <div className="materials-workspace">
      <div className="workspace-intro"><div><p className="eyebrow">步骤 02 · 资料</p><h2>先核对材料，再决定分析范围</h2><p>系统只把解析后的内容块交给 AI。你可以逐块选择，也可以在分析页明确选择整个项目。</p></div><span className="selection-counter">已选 {selectedBlockIds.length} 块</span></div>
      <SourceUploader busy={upload.isPending} onUpload={accept} />
      {(localError || apiError) && <div className="source-warning is-error" role="alert"><AlertTriangle /><div><strong>资料未能入库</strong><p>{localError || apiError?.message}</p><button className="button button--secondary" type="button" onClick={() => setLocalError('')}>重新选择文件</button></div></div>}
      {upload.isSuccess && <div className="source-warning is-success" role="status"><CheckCircle2 /><div><strong>资料已加入索引</strong><p>{upload.data.cache === 'hit' ? '已命中本机解析缓存，没有重复处理。' : `已生成 ${upload.data.block_count} 个内容块；请查看资料状态与解析提醒。`}</p></div></div>}

      {sources.isPending && <LoadingState label="正在读取资料索引" />}
      {sources.isError && <ErrorState title="资料索引未能加载" description="本机服务可能暂时不可用。" onRetry={() => void sources.refetch()} />}
      {sources.data && !sources.data.items.length && <EmptyState title="还没有资料" description="从上方上传第一份题目或复习材料。解析完成后，你可以精确选择交给 AI 的内容。" />}
      {sources.data && sources.data.items.length > 0 && (
        <div className="materials-ledger">
          <aside className="source-index" aria-label="资料列表">
            <header><span>资料索引</span><strong>{sources.data.total}</strong></header>
            {sources.data.items.map((source, index) => (
              <button type="button" key={source.id} className={activeSource?.id === source.id ? 'is-active' : ''} onClick={() => setActiveSourceId(source.id)}>
                <span>{String(index + 1).padStart(2, '0')}</span><span><strong>{source.display_name}</strong><small>{source.page_count ?? '—'} 页 · {statusLabel[source.parse_status]}</small></span><b className="file-extension">{source.extension.replace('.', '')}</b>
              </button>
            ))}
          </aside>
          {activeSource && <section className="source-sheet"><div className="section-heading"><div><p className="eyebrow">当前资料 · {activeSource.display_name}</p><h2>解析内容与选择范围</h2></div><button className="icon-button" type="button" aria-label={`删除 ${activeSource.display_name}`} disabled={remove.isPending} onClick={() => window.confirm('删除这份资料及其分析结果？') && remove.mutate(activeSource)}><Trash2 /></button></div>{activeSource.warnings.map((warning) => <div className="source-warning" key={warning}><AlertTriangle /><div><strong>{statusLabel[activeSource.parse_status]}</strong><p>{warning}</p></div></div>)}<SourcePreview source={activeSource} selectedBlockIds={selectedBlockIds} onSelectedBlockIdsChange={onSelectedBlockIdsChange} /></section>}
        </div>
      )}
    </div>
  )
}
