import type { ReactNode } from 'react'
import { AlertCircle, LoaderCircle, Plus } from 'lucide-react'

export function PageHeading({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow: string
  title: string
  description?: string
  actions?: ReactNode
}) {
  return (
    <header className="page-heading">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        {description && <p className="page-description">{description}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </header>
  )
}

export function LoadingState({ label = '正在读取本机数据' }: { label?: string }) {
  return (
    <div className="state-panel" role="status">
      <LoaderCircle className="spin" aria-hidden="true" />
      <p>{label}</p>
    </div>
  )
}

export function EmptyState({
  title,
  description,
  actionLabel,
  onAction,
}: {
  title: string
  description: string
  actionLabel?: string
  onAction?: () => void
}) {
  return (
    <div className="state-panel state-panel--empty">
      <span className="empty-mark" aria-hidden="true"><Plus /></span>
      <h2>{title}</h2>
      <p>{description}</p>
      {actionLabel && onAction && (
        <button className="button button--primary" type="button" onClick={onAction}>
          {actionLabel}
        </button>
      )}
    </div>
  )
}

export function ErrorState({
  title,
  description,
  onRetry,
}: {
  title: string
  description: string
  onRetry?: () => void
}) {
  return (
    <div className="state-panel state-panel--error" role="alert">
      <AlertCircle aria-hidden="true" />
      <h2>{title}</h2>
      <p>{description}</p>
      {onRetry && (
        <button className="button button--secondary" type="button" onClick={onRetry}>
          重新加载
        </button>
      )}
    </div>
  )
}
