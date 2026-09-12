type LoadingStateProps = {
  label: string
  rows?: number
}

export function LoadingState({ label, rows = 4 }: LoadingStateProps) {
  return (
    <div aria-busy="true" aria-live="polite">
      <p className="muted" style={{ marginBottom: 8 }}>
        {label}
      </p>
      {Array.from({ length: rows }, (_, index) => (
        <div className="skeleton-row" key={index} />
      ))}
    </div>
  )
}
