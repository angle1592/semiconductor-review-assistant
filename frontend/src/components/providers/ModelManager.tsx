import type { ModelProfile } from '../../api/client'
import { CapabilityBadges } from './CapabilityBadges'

export function ModelManager({ models, selectedId, onSelect, onProbe, probing }: { models: ModelProfile[]; selectedId: string; onSelect: (id: string) => void; onProbe: () => void; probing: boolean }) {
  const selected = models.find((model) => model.id === selectedId)
  return <div className="model-manager"><label>模型<select value={selectedId} onChange={(event) => onSelect(event.target.value)}><option value="">请选择模型</option>{models.map((model) => <option key={model.id} value={model.id}>{model.display_name} · {model.model_id}</option>)}</select></label>{selected && <CapabilityBadges model={selected} />}<button className="button button--secondary" type="button" disabled={!selected || probing} onClick={onProbe}>{probing ? '正在校验…' : '校验模型能力'}</button></div>
}
