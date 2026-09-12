import { EmptyState } from '../../components/EmptyState'
import type { ModelingBaseline, ModelingDraftRecord, ModelingRun } from '../../api/types'
import { useI18n } from '../../i18n'
import { freezeBaseline, errorMessage } from '../../api/client'
import { formatTimestamp } from '../../lib/format'
import { canFreezeSelectedDraft, selectBaselineDraft, selectLatestModelingRun } from '../../lib/sourceView'
import { useMemo, useState } from 'react'

const IN_FLIGHT = new Set(['queued', 'running', 'waiting_for_user'])

type BaselineWorkspaceProps = {
  projectId: string
  baselines: ModelingBaseline[]
  drafts: ModelingDraftRecord[]
  runs: ModelingRun[]
  currentBaselineId?: string | null
  reload: () => Promise<void> | void
}

function sortBaselines(rows: ModelingBaseline[]): ModelingBaseline[] {
  return [...rows].sort((left, right) => {
    const byTime = (right.created_at || '').localeCompare(left.created_at || '')
    if (byTime !== 0) return byTime
    return (right.draft_revision_no ?? 0) - (left.draft_revision_no ?? 0)
  })
}

export function BaselineWorkspace({
  projectId,
  baselines,
  drafts,
  runs,
  currentBaselineId,
  reload,
}: BaselineWorkspaceProps) {
  const { locale, t } = useI18n()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [exporting, setExporting] = useState<'md' | 'json' | null>(null)
  const [exportError, setExportError] = useState<string | null>(null)
  const [exportFailedKind, setExportFailedKind] = useState<'md' | 'json' | null>(null)
  const ordered = useMemo(() => sortBaselines(baselines), [baselines])
  const currentId = currentBaselineId || ordered[0]?.id || null
  const [selectedId, setSelectedId] = useState<string | null>(currentId)
  const [seenCurrentId, setSeenCurrentId] = useState<string | null>(currentBaselineId ?? null)
  if ((currentBaselineId ?? null) !== seenCurrentId) {
    setSeenCurrentId(currentBaselineId ?? null)
    if (currentBaselineId) setSelectedId(currentBaselineId)
  }
  const selected = ordered.find((item) => item.id === selectedId) ?? ordered[0]
  const latestRun = useMemo(() => selectLatestModelingRun(runs, null), [runs])
  const latestDraft = useMemo(() => selectBaselineDraft(drafts, runs), [drafts, runs])
  const canFreeze = canFreezeSelectedDraft(latestDraft, latestRun?.id)
  const runInFlight = Boolean(latestRun && IN_FLIGHT.has(latestRun.status))

  async function onFreeze() {
    if (!canFreeze || !latestDraft || busy) return
    setBusy(true)
    setError(null)
    try {
      const frozen = await freezeBaseline(projectId, latestDraft.id)
      setSelectedId(frozen.id)
      await reload()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  async function onExport(kind: 'md' | 'json') {
    if (!selected || exporting) return
    setExporting(kind)
    setExportError(null)
    setExportFailedKind(null)
    try {
      const response = await fetch(`/api/baselines/${selected.id}/export.${kind}`)
      if (!response.ok) {
        throw new Error(`${response.status} ${response.statusText}`)
      }
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `lucid-baseline-${selected.id.slice(0, 8)}.${kind}`
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(url)
    } catch (err) {
      setExportFailedKind(kind)
      setExportError(errorMessage(err))
    } finally {
      setExporting(null)
    }
  }

  if (baselines.length === 0) {
    return (
      <div className="stage">
        <p className="muted">{t('baselineJob')}</p>
        {canFreeze ? (
          <p>
            <button className="btn btn-primary" type="button" disabled={busy} onClick={() => void onFreeze()}>
              {busy ? t('freezing') : t('freezeBaseline')}
            </button>
          </p>
        ) : (
          <EmptyState
            title={runInFlight ? t('draftInProgress') : t('noDraft')}
            body={runInFlight ? t('draftInProgressBody') : latestRun ? t('runHasNoDraftBody') : t('freezeOnBaseline')}
          />
        )}
        {error ? <p role="alert">{error}</p> : null}
      </div>
    )
  }

  return (
    <div className="stage">
      <p className="muted">{t('frozenAlready')}</p>
      {ordered.length > 1 ? (
        <div className="stack">
          <h3>{t('historicalBaselines')}</h3>
          <ul className="coverage-list">
            {ordered.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  className={item.id === selected?.id ? 'active' : ''}
                  aria-current={item.id === currentId ? 'true' : undefined}
                  onClick={() => setSelectedId(item.id)}
                >
                  {item.id.slice(0, 8)} · {formatTimestamp(item.created_at, locale, t)}
                  {item.id === currentId ? ` · ${t('currentVersion')}` : ''}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {selected ? (
        <article className="fact present">
          <div className="fact-label">{t('currentBaseline')}</div>
          <p>{t('selectedBaseline')} {selected.id}</p>
          <p>{t('draftRevision')} {selected.draft_revision_no ?? t('none')}</p>
          <p>{t('frozenAt')} {formatTimestamp(selected.created_at, locale, t)}</p>
          <p>{t('sourceCount')} {selected.source_count ?? t('none')}</p>
          <p>{t('claimCount')} {selected.claim_count ?? t('none')}</p>
          <p>{t('baselineImmutable')}: {String(selected.immutable ?? true)}</p>
          <p>{t('solver')}: {selected.solver}</p>
          <div className="review-actions">
            <button
              className="btn btn-secondary"
              type="button"
              disabled={exporting != null}
              aria-busy={exporting === 'md'}
              aria-disabled={exporting != null}
              onClick={() => void onExport('md')}
            >
              {exporting === 'md' ? t('exportingMarkdown') : t('exportMarkdown')}
            </button>
            <button
              className="btn btn-secondary"
              type="button"
              disabled={exporting != null}
              aria-busy={exporting === 'json'}
              aria-disabled={exporting != null}
              onClick={() => void onExport('json')}
            >
              {exporting === 'json' ? t('exportingJson') : t('exportJson')}
            </button>
          </div>
          {exportError ? (
            <p role="alert">
              {t('exportFailed')}
              {exportFailedKind ? ` (${exportFailedKind})` : ''} {exportError}{' '}
              <button
                className="btn btn-ghost"
                type="button"
                disabled={exporting != null || exportFailedKind == null}
                aria-busy={exporting != null && exporting === exportFailedKind}
                onClick={() => exportFailedKind && void onExport(exportFailedKind)}
              >
                {t('retryExport')}
              </button>
            </p>
          ) : null}
          <pre className="source-text">{selected.markdown}</pre>
          <details className="tech-details">
            <summary>{t('technicalDetails')}</summary>
            <pre>{JSON.stringify(selected.handoff, null, 2)}</pre>
          </details>
        </article>
      ) : null}
      {error ? <p role="alert">{error}</p> : null}
    </div>
  )
}
