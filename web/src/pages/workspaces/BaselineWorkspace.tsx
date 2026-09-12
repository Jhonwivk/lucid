import { EmptyState } from '../../components/EmptyState'
import type { ModelingBaseline, ModelingDraftRecord } from '../../api/types'
import { useI18n } from '../../i18n'
import { freezeBaseline, errorMessage } from '../../api/client'
import { formatTimestamp } from '../../lib/format'
import { useState } from 'react'

type BaselineWorkspaceProps = {
  projectId: string
  baselines: ModelingBaseline[]
  drafts: ModelingDraftRecord[]
  reload: () => Promise<void> | void
}

export function BaselineWorkspace({ projectId, baselines, drafts, reload }: BaselineWorkspaceProps) {
  const { locale, t } = useI18n()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const latestDraft = drafts[drafts.length - 1] ?? null
  const latest = baselines[baselines.length - 1]
  const canFreeze = latestDraft && latestDraft.version_state !== 'confirmed'

  async function onFreeze() {
    if (!latestDraft || busy) return
    setBusy(true)
    setError(null)
    try {
      await freezeBaseline(projectId, latestDraft.id)
      await reload()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
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
          <EmptyState title={t('noDraft')} body={t('freezeOnBaseline')} />
        )}
        {error ? <p role="alert">{error}</p> : null}
      </div>
    )
  }

  return (
    <div className="stage">
      <p className="muted">{t('frozenAlready')}</p>
      <article className="fact present">
        <div className="fact-label">{t('baseline')}</div>
        <p>{t('recorded')} {formatTimestamp(latest.created_at, locale, t)}</p>
        <p>{t('solver')}: {latest.solver}</p>
        <div className="review-actions">
          <a className="btn btn-secondary" href={`/api/baselines/${latest.id}/export.md`}>{t('exportMarkdown')}</a>
          <a className="btn btn-secondary" href={`/api/baselines/${latest.id}/export.json`}>{t('exportJson')}</a>
        </div>
        <pre className="source-text">{latest.markdown}</pre>
        <details className="tech-details">
          <summary>{t('technicalDetails')}</summary>
          <pre>{JSON.stringify(latest.handoff, null, 2)}</pre>
        </details>
      </article>
      {error ? <p role="alert">{error}</p> : null}
    </div>
  )
}
