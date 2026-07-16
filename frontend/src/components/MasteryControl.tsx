import type { MasteryLevel } from '../api/mastery'

const options: { value: MasteryLevel; label: string }[] = [{ value: 'learning', label: '学习中' }, { value: 'familiar', label: '已熟悉' }, { value: 'mastered', label: '已掌握' }]

export function MasteryControl({ value = 'unrated', disabled, onChange }: { value?: MasteryLevel; disabled?: boolean; onChange: (value: MasteryLevel) => void }) {
  return <fieldset className="mastery-control"><legend>掌握程度</legend>{options.map((option) => <button type="button" key={option.value} className={value === option.value ? 'is-active' : ''} disabled={disabled} aria-pressed={value === option.value} onClick={() => onChange(option.value)}>{option.label}</button>)}</fieldset>
}
