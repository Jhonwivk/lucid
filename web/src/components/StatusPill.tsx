import type { LoadState } from '../api/types'

type StatusPillProps = {
  state: LoadState
  label: string
}

export function StatusPill({ state, label }: StatusPillProps) {
  const tone = state === 'ready' ? 'ok' : state === 'error' ? 'err' : 'warn'
  return (
    <span className="pill">
      <span className={`dot ${tone}`} aria-hidden />
      {label}
    </span>
  )
}
