import { Edit3, ExternalLink, Save, X } from 'lucide-react'
import { useState, type FormEvent } from 'react'

import type { Candidate, Importance } from '../api/keypoints'

const importanceLabels: Record<Importance, string> = { core: '核心', important: '重要', supplementary: '补充' }

export function KeyPointCandidateCard({ candidate, selected, saving, onSelectedChange, onSave, onOpenSource }: { candidate: Candidate; selected: boolean; saving: boolean; onSelectedChange: (selected: boolean) => void; onSave: (value: Pick<Candidate, 'title' | 'explanation' | 'importance' | 'rationale'>) => void; onOpenSource: (blockId: string) => void }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState({ title: candidate.title, explanation: candidate.explanation, importance: candidate.importance, rationale: candidate.rationale })
  function submit(event: FormEvent) { event.preventDefault(); onSave(draft); setEditing(false) }

  return (
    <article className={`candidate-card is-${candidate.importance}`}>
      <label className="candidate-select"><input type="checkbox" checked={selected} aria-label={`选择候选 ${candidate.title}`} onChange={(event) => onSelectedChange(event.target.checked)} /><span>{candidate.status === 'pending' ? '待确认' : candidate.status === 'confirmed' ? '已确认' : '已拒绝'}</span></label>
      {editing ? (
        <form className="candidate-editor" onSubmit={submit}>
          <label>候选标题<input aria-label="候选标题" value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} /></label>
          <label>解释<textarea value={draft.explanation} onChange={(event) => setDraft({ ...draft, explanation: event.target.value })} /></label>
          <label>重要程度<select value={draft.importance} onChange={(event) => setDraft({ ...draft, importance: event.target.value as Importance })}><option value="core">核心</option><option value="important">重要</option><option value="supplementary">补充</option></select></label>
          <label>判断理由<textarea value={draft.rationale} onChange={(event) => setDraft({ ...draft, rationale: event.target.value })} /></label>
          <div className="candidate-toolbar"><button className="button button--primary" type="submit" disabled={saving}><Save /> 保存候选修改</button><button className="button button--ghost" type="button" onClick={() => setEditing(false)}><X /> 取消</button></div>
        </form>
      ) : (
        <div className="candidate-copy">
          <div><span className="candidate-importance">{importanceLabels[candidate.importance]}</span><h3>{candidate.title}</h3></div>
          <p>{candidate.explanation}</p>
          <blockquote>{candidate.evidence_quotes.join('；')}</blockquote>
          <small>AI 判断理由：{candidate.rationale}</small>
          <div className="candidate-toolbar"><button className="button button--secondary" type="button" aria-label={`编辑 ${candidate.title}`} onClick={() => setEditing(true)}><Edit3 /> 编辑</button>{candidate.source_block_ids.map((id, index) => <button className="button button--ghost" type="button" key={id} onClick={() => onOpenSource(id)}><ExternalLink /> 来源 {index + 1}</button>)}</div>
        </div>
      )}
    </article>
  )
}
