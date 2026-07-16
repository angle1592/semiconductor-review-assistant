import type { ModelProfile } from '../../api/client'

const labels = { text_status: '文本', structured_status: '结构化', vision_status: '视觉', prompt_cache_status: '缓存' } as const
const statusText: Record<string, string> = { passed: '通过', failed: '失败', unsupported: '不支持', untested: '未校验' }

export function CapabilityBadges({ model }: { model: ModelProfile }) {
  return <div className="capability-badges" aria-label="模型能力">{Object.entries(labels).map(([field, label]) => {
    const status = model[field as keyof ModelProfile] as string
    return <span key={field} className={`capability-badge is-${status}`}>{label}：{statusText[status] ?? status}</span>
  })}</div>
}
