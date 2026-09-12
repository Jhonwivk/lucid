import { EmptyState } from '../../components/EmptyState'
import type { FormalModelDefinition, ModelingBaseline, ModelingDraftRecord, ModelingRun, Scenario } from '../../api/types'
import { useI18n } from '../../i18n'
import { createScenarioFromBaseline, freezeBaseline, errorMessage } from '../../api/client'
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
  scenarios: Scenario[]
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
  scenarios,
  reload,
}: BaselineWorkspaceProps) {
  const { locale, t } = useI18n()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [exporting, setExporting] = useState<'md' | 'json' | null>(null)
  const [exportError, setExportError] = useState<string | null>(null)
  const [exportFailedKind, setExportFailedKind] = useState<'md' | 'json' | null>(null)
  const [scenarioName, setScenarioName] = useState('Scenario v1')
  const [scenarioBusy, setScenarioBusy] = useState(false)
  const [scenarioError, setScenarioError] = useState<string | null>(null)
  const ordered = useMemo(() => sortBaselines(baselines), [baselines])
  const currentId = currentBaselineId || ordered[0]?.id || null
  const [selectedId, setSelectedId] = useState<string | null>(currentId)
  const [seenCurrentId, setSeenCurrentId] = useState<string | null>(currentBaselineId ?? null)
  if ((currentBaselineId ?? null) !== seenCurrentId) {
    setSeenCurrentId(currentBaselineId ?? null)
    if (currentBaselineId) setSelectedId(currentBaselineId)
  }
  const selected = ordered.find((item) => item.id === selectedId) ?? ordered[0]
  const boundScenario = selected?.scenario_id ? scenarios.find((scenario) => scenario.id === selected.scenario_id) : undefined
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

  async function onCreateScenario() {
    if (!selected || selected.scenario_id || scenarioBusy || !scenarioName.trim()) return
    setScenarioBusy(true)
    setScenarioError(null)
    try {
      await createScenarioFromBaseline(projectId, selected.id, {
        name: scenarioName.trim(),
        expected_baseline_id: selected.id,
        notes: 'Created from the confirmed baseline for formalization and solving.',
      })
      await reload()
    } catch (err) {
      setScenarioError(errorMessage(err))
    } finally {
      setScenarioBusy(false)
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
      {canFreeze ? (
        <p>
          <button className="btn btn-primary" type="button" disabled={busy} onClick={() => void onFreeze()}>
            {busy ? t('freezing') : t('freezeBaseline')}
          </button>
        </p>
      ) : runInFlight ? (
        <EmptyState title={t('draftInProgress')} body={t('draftInProgressBody')} />
      ) : null}
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
          <section className="stage2-formalization" aria-labelledby="stage2-formalization-heading">
            <div className="fact-label" id="stage2-formalization-heading">{t('formalizationFlow')}</div>
            {selected.scenario_id ? (
              <p className="muted">{t('baselineBoundToScenario')} {selected.scenario_id}</p>
            ) : (
              <>
                <p className="muted">{t('baselineToScenarioHint')}</p>
                <div className="inline-form">
                  <label className="field">
                    <span>{t('scenarioName')}</span>
                    <input value={scenarioName} onChange={(event) => setScenarioName(event.target.value)} maxLength={120} />
                  </label>
                  <button className="btn btn-primary" type="button" disabled={scenarioBusy || !scenarioName.trim()} onClick={() => void onCreateScenario()}>
                    {scenarioBusy ? t('creatingScenario') : t('createScenarioFormalModel')}
                  </button>
                </div>
              </>
            )}
            {scenarioError ? <p className="muted" role="alert">{scenarioError}</p> : null}
            {boundScenario ? <ScenarioFormalSummary scenario={boundScenario} /> : null}
          </section>
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

function ScenarioFormalSummary({ scenario }: { scenario: Scenario }) {
  const { t } = useI18n()
  const latest = scenario.revisions[scenario.revisions.length - 1]
  const model = latest?.formal_model
  const definition = model?.definition
  return (
    <div className="stage2-flow" data-testid="stage2-formal-model">
      <div className="flow-step complete"><strong>{t('confirmedBaseline')}</strong><span>{scenario.name}</span></div>
      <div className="flow-arrow" aria-hidden="true">↓</div>
      <div className="flow-step complete"><strong>{t('scenarioRevision')}</strong><span>v{latest?.revision_no ?? '—'} · {latest?.version_state ?? '—'}</span></div>
      <div className="flow-arrow" aria-hidden="true">↓</div>
      <div className={`flow-step ${model?.validation?.valid ? 'complete' : 'warning'}`}>
        <strong>{t('formalModel')}</strong>
        <span>{model?.name ?? t('noFormalModel')}</span>
        {model ? <FormalDefinitionSummary definition={definition} model={model} /> : null}
      </div>
    </div>
  )
}

function FormalDefinitionSummary({ definition, model }: { definition?: FormalModelDefinition | null; model: NonNullable<Scenario['revisions'][number]['formal_model']> }) {
  const { t } = useI18n()
  const validation = model.validation ?? {}
  const issues = Array.isArray(validation.issues) ? validation.issues : []
  return (
    <>
      <div className="meta-row">
        <span>{t('variables')}: {definition?.variables.length ?? model.variable_count ?? '—'}</span>
        <span>{t('constraints')}: {definition?.constraints.length ?? model.constraint_count ?? '—'}</span>
        <span>{t('objectives')}: {definition?.objectives.length ?? '—'}</span>
      </div>
      <p className={`validation-badge ${validation.valid ? 'valid' : 'invalid'}`}>
        {validation.valid ? t('formalModelReady') : t('formalModelNeedsReview')}
      </p>
      {issues.length ? <ul className="issue-list">{issues.map((issue) => <li key={issue}>{issue}</li>)}</ul> : null}
      {definition?.training_schedule ? <p className="muted">{t('trainingScheduleInputs')}: {definition.training_schedule.sessions.length} {t('sessions')}, {definition.training_schedule.time_slots.length} {t('timeSlots')}, {definition.training_schedule.rooms.length} {t('rooms')}, {definition.training_schedule.instructors.length} {t('instructors')}</p> : null}
    </>
  )
}
