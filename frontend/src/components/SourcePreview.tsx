import { useQuery } from '@tanstack/react-query'
import { FileText, ImageOff } from 'lucide-react'

import { API_BASE_URL } from '../api/client'
import { sourceKeys, sourcesApi, type SourceDocument } from '../api/sources'
import { ErrorState, LoadingState } from './Ui'

export function SourcePreview({ source, selectedBlockIds, onSelectedBlockIdsChange }: { source: SourceDocument; selectedBlockIds: string[]; onSelectedBlockIdsChange: (ids: string[]) => void }) {
  const blocks = useQuery({ queryKey: sourceKeys.blocks(source.id), queryFn: () => sourcesApi.blocks(source.id) })
  if (blocks.isPending) return <LoadingState label="正在展开资料内容" />
  if (blocks.isError) return <ErrorState title="资料内容未能加载" description="请检查本机服务后重试。" onRetry={() => void blocks.refetch()} />
  if (!blocks.data.items.length) return <div className="inline-guidance"><FileText /><p>这份资料没有可选择的文本块。若解析有提醒，请先查看上方说明。</p></div>

  function toggle(id: string, checked: boolean) {
    onSelectedBlockIdsChange(checked ? [...new Set([...selectedBlockIds, id])] : selectedBlockIds.filter((item) => item !== id))
  }

  return (
    <div className="source-preview">
      <div className="section-heading"><div><p className="eyebrow">内容索引</p><h3>{blocks.data.total} 个内容块</h3></div><span className="selection-counter">已选 {blocks.data.items.filter((block) => selectedBlockIds.includes(block.id)).length}</span></div>
      <div className="block-ledger">
        {blocks.data.items.map((block) => (
          <article className="block-row" key={block.id}>
            <label className="block-selector">
              <input type="checkbox" checked={selectedBlockIds.includes(block.id)} onChange={(event) => toggle(block.id, event.target.checked)} />
              <span>{String(block.ordinal + 1).padStart(3, '0')}</span>
            </label>
            <div>
              <small>{block.heading_path.join(' / ') || block.locator}{block.page_number ? ` · 第 ${block.page_number} 页` : ''}</small>
              <p>{block.text}</p>
            </div>
            {block.preview_path ? <img src={`${API_BASE_URL}/api/sources/${source.id}/preview/${block.preview_path}`} alt={`第 ${block.page_number ?? block.ordinal + 1} 页预览`} /> : <ImageOff className="preview-missing" aria-label="无页面预览" />}
          </article>
        ))}
      </div>
    </div>
  )
}
