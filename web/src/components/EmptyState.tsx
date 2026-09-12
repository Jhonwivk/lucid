import type { ReactNode } from 'react'

type EmptyStateProps = {
  title: string
  body: string
  action?: ReactNode
}

export function EmptyState({ title, body, action }: EmptyStateProps) {
  return (
    <div className="state-panel">
      <h2>{title}</h2>
      <p>{body}</p>
      {action ? <div style={{ marginTop: 16 }}>{action}</div> : null}
    </div>
  )
}
