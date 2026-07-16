import { Check, Power, RefreshCw, Star, Trash2 } from 'lucide-react'
import type { ModelProfile, ProviderProfile } from '../../api/client'
import { CapabilityBadges } from './CapabilityBadges'

export function ProviderCard({ provider, models, onEdit, onRefresh, onToggle, onDefault, onDelete }: { provider: ProviderProfile; models: ModelProfile[]; onEdit: () => void; onRefresh: () => void; onToggle: () => void; onDefault: () => void; onDelete: () => void }) {
  const validated = models.find((model) => model.text_status === 'passed')
  return <article className="provider-card"><header><div><p className="eyebrow">{provider.protocol === 'anthropic' ? 'Anthropic' : 'OpenAI 兼容'}</p><h2>{provider.name}</h2></div><div className="provider-card__status">{provider.is_default && <span><Star />默认</span>}{provider.enabled ? <span className="is-online"><Check />已启用</span> : <span>已停用</span>}</div></header><code>{provider.base_url}</code>{validated ? <CapabilityBadges model={validated} /> : <p className="field-hint">尚无通过校验的模型。</p>}<footer><button className="button button--ghost" type="button" onClick={onEdit}>编辑</button><button className="button button--ghost" type="button" onClick={onRefresh}><RefreshCw />刷新模型</button><button className="button button--ghost" type="button" onClick={onToggle}><Power />{provider.enabled ? '停用' : '启用'}</button>{provider.enabled && !provider.is_default && <button className="button button--ghost" type="button" onClick={onDefault}>设为默认</button>}<button className="button button--danger" type="button" onClick={onDelete}><Trash2 />删除</button></footer></article>
}
