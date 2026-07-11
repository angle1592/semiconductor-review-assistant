const stages = ['R+0', 'R+2', 'R+7', 'R+21', 'R+60'] as const

type WaferStagesProps = {
  active?: number
  compact?: boolean
}

export function WaferStages({ active = 0, compact = false }: WaferStagesProps) {
  return (
    <div className={`wafer-stages${compact ? ' wafer-stages--compact' : ''}`} aria-label="复习阶段">
      {stages.map((stage, index) => (
        <div className="wafer-stage-wrap" key={stage}>
          <div
            className={`wafer-stage${index < active ? ' is-past' : ''}${index === active ? ' is-active' : ''}`}
            aria-current={index === active ? 'step' : undefined}
          >
            <span>{stage}</span>
          </div>
          {index < stages.length - 1 && <span className="wafer-track" aria-hidden="true" />}
        </div>
      ))}
    </div>
  )
}
