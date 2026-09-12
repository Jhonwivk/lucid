import type { ReactNode } from 'react'

type ErrorStateProps = {
  title: string
  body: string
  action?: ReactNode
}

export function ErrorState({ title, body, action }: ErrorStateProps) {
  return (
    <div className="state-panel error" role="alert">
      <h2>{title}</h2>
      <p>{body}</p>
      {action ? <div style={{ marginTop: 16 }}>{action}</div> : null}
    </div>
  )
}
