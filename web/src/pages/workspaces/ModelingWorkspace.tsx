import { useEffect, useMemo, useState } from 'react'
import {
  cancelModelingRun,
  errorMessage,
  freezeBaseline,
  getModelingRun,
  listClaimHistory,
  resumeModelingRun,
  reviewClaim,
  startModelingRun,
} from '../../api/client'
import type {
  ClaimReviewEvent,
  Material,
  ModelingClaim,
  ModelingDraftRecord,
  ModelingRun,
  ReadinessPayload,
  SourceSpan,
} from '../../api/types'
import { SourceViewer, type SourceHighlight } from '../../components/SourceViewer'
import { EmptyState } from '../../components/EmptyState'
import { useI18n, type Translate } from '../../i18n'
import {
  claimKindHeading,
  coverageLabel,
  reviewLabel,
  sourceRefLabel,
} from '../../lib/format'
import {
  materialFromSnapshot,
  selectDraftForRun,
  selectLatestModelingRun,
  snapshotRunIdForSelection,
} from '../../lib/sourceView'

type ModelingWorkspaceProps = {
  projectId: string
  question: string
  materials: Material[]
  sourceSpans: SourceSpan[]
  runs: ModelingRun[]
  drafts: ModelingDraftRecord[]
  readiness: ReadinessPayload
  reload: () => Promise<void> | void
}

const ACTIVE = new Set(['queued', 'running'])
const START_BLOCKED = new Set(['queued', 'running', 'waiting_for_user'])
const REVIEW_KINDS = [
  'constraint',
  'objective',
  'unknown',
  'conflict',
  'parameter',
  'entity',
  'assumption',
  'variable',
  'readiness',
] as const

function runStatusLabel(status: string, t: Translate): string {
  switch (status) {
    case 'queued':
      return t('queued')
    case 'running':
      return t('running')
    case 'waiting_for_user':
      return t('waitingForUser')
    case 'failed':
      return t('modelingRunFailed')
    case 'partial':
      return t('partialDraft')
    case 'completed':
      return t('completedDraft')
    case 'cancelled':
      return t('runCancelled')
    default:
      return status
  }
}

function missingModelKeys(readiness: ReadinessPayload): string[] {
  const missing: string[] = []
  if (!readiness.model.name_present) missing.push('LUCID_MODEL_NAME')
  if (!readiness.model.base_url_present) missing.push('LUCID_MODEL_BASE_URL')
  if (!readiness.model.api_key_present) missing.push('LUCID_MODEL_API_KEY')
  return missing
}

export function ModelingWorkspace({
  projectId,
  question,
  materials,
  sourceSpans,
  runs,
  drafts,
  readiness,
  reload,
}: ModelingWorkspaceProps) {
  const { t } = useI18n()
  const [pane, setPane] = useState<'sources' | 'claims' | 'activity'>('claims')
  const [selectedId, setSelectedId] = useState<string | null>(materials[0]?.id ?? null)
  const [focusClaimId, setFocusClaimId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [historyError, setHistoryError] = useState<string | null>(null)
  const [answer, setAnswer] = useState('')
  const [editId, setEditId] = useState<string | null>(null)
  const [editText, setEditText] = useState('')
  const [historyId, setHistoryId] = useState<string | null>(null)
  const [history, setHistory] = useState<ClaimReviewEvent[]>([])
  const [pinnedRunId, setPinnedRunId] = useState<string | null>(null)
  const [polledRun, setPolledRun] = useState<ModelingRun | null>(null)
  const latestFromList = useMemo(
    () => selectLatestModelingRun(runs, pinnedRunId),
    [runs, pinnedRunId],
  )
  const latestRun = polledRun && latestFromList && polledRun.id === latestFromList.id
    ? { ...latestFromList, ...polledRun }
    : latestFromList
  const latestRunId = latestRun?.id ?? null
  const latestDraft = useMemo(() => selectDraftForRun(drafts, latestRunId), [drafts, latestRunId])
  const canMutateDraft = Boolean(
    latestDraft
    && latestRunId
    && latestDraft.run_id === latestRunId
    && latestDraft.version_state !== 'confirmed',
  )
  const runInFlight = Boolean(
    latestRun && (ACTIVE.has(latestRun.status) || latestRun.status === 'waiting_for_user'),
  )
  const pending = latestRun?.clarifications.find((item) => item.status === 'pending') ?? null
  const snapshotMaterials = latestRun?.snapshot?.materials
  const selectedSnapshot = snapshotMaterials?.find((item) => item.id === selectedId) ?? null
  const liveSelected = materials.find((item) => item.id === selectedId) ?? null
  const selected = selectedSnapshot
    ? materialFromSnapshot(projectId, selectedSnapshot, liveSelected, latestRun?.created_at ?? '')
    : liveSelected
  const snapshotRunId = snapshotRunIdForSelection(latestRun, selectedId)
  const selectedSpans = useMemo(() => {
    const snap = snapshotMaterials?.find((item) => item.id === selectedId)
    if (snap?.spans?.length) return snap.spans
    return sourceSpans.filter((span) => span.material_id === selectedId)
  }, [snapshotMaterials, selectedId, sourceSpans])
  const claims = useMemo(
    () => latestDraft?.claims.filter((claim) => REVIEW_KINDS.includes(claim.claim_kind as typeof REVIEW_KINDS[number])) ?? [],
    [latestDraft],
  )
  const focused = claims.find((claim) => claim.id === focusClaimId) ?? claims.find((claim) =>
    claim.evidence_refs.some((ref) => ref.material_id === selected?.id),
  )
  const highlight = useMemo<SourceHighlight | undefined>(() => {
    const ref = focused?.evidence_refs.find((item) => item.material_id === selected?.id) ?? focused?.evidence_refs[0]
    if (!ref) return undefined
    return {
      start: ref.start_offset,
      end: ref.end_offset,
      page: ref.page,
      sheet: ref.sheet,
      cell: ref.cell_ref,
      precision: ref.precision,
      region: ref.region,
    }
  }, [focused, selected])
  const related = useMemo(
    () => claims.filter((claim) => claim.evidence_refs.some((ref) => ref.material_id === selected?.id)),
    [claims, selected],
  )

  const pollRunId = latestRun && ACTIVE.has(latestRun.status) ? latestRun.id : null

  useEffect(() => {
    if (!pollRunId) return
    const timer = window.setInterval(() => {
      void getModelingRun(pollRunId)
        .then((payload) => {
          if (payload.id !== pollRunId) return
          setPolledRun(payload)
          if (!ACTIVE.has(payload.status)) void reload()
        })
        .catch((err: unknown) => setError(errorMessage(err)))
    }, 1500)
    return () => window.clearInterval(timer)
  }, [pollRunId, reload])

  const modelReady = readiness.live_agent_possible
  const missingKeys = missingModelKeys(readiness)
  const runBusy = Boolean(latestRun && START_BLOCKED.has(latestRun.status))
  const canStart = !busy && !runBusy && Boolean(question.trim()) && modelReady

  async function onStart() {
    if (!canStart) return
    setBusy(true)
    setError(null)
    try {
      const started = await startModelingRun(projectId, question || t('decisionQuestion'))
      setPinnedRunId(started.id)
      setPolledRun(started)
      await reload()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  async function onResume() {
    if (!latestRun || !answer.trim() || busy) return
    setBusy(true)
    setError(null)
    try {
      const resumed = await resumeModelingRun(latestRun.id, answer.trim())
      setPinnedRunId(resumed.id)
      setPolledRun(resumed)
      setAnswer('')
      await reload()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  async function onCancel() {
    if (!latestRun || cancelling) return
    setCancelling(true)
    setError(null)
    try {
      const cancelled = await cancelModelingRun(latestRun.id)
      setPolledRun(cancelled)
      await reload()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setCancelling(false)
    }
  }

  async function onReview(claim: ModelingClaim, action: string, edited?: string) {
    if (!canMutateDraft) return
    setBusy(true)
    setError(null)
    try {
      await reviewClaim(claim.id, action, edited)
      setEditId(null)
      if (historyId === claim.id) {
        try {
          setHistory(await listClaimHistory(claim.id))
          setHistoryError(null)
        } catch (err) {
          setHistoryError(errorMessage(err))
        }
      }
      await reload()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  async function onFreeze() {
    if (!canMutateDraft || !latestDraft || busy) return
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

  async function onHistory(claimId: string) {
    if (historyId === claimId) {
      setHistoryId(null)
      setHistory([])
      setHistoryError(null)
      return
    }
    setHistoryId(claimId)
    setHistoryError(null)
    try {
      setHistory(await listClaimHistory(claimId))
    } catch (err) {
      setHistory([])
      setHistoryError(errorMessage(err))
    }
  }

  const grouped = REVIEW_KINDS.map((kind) => ({
    kind,
    items: claims.filter((claim) => claim.claim_kind === kind),
  })).filter((group) => group.items.length > 0)
  const sourceList = snapshotMaterials && snapshotMaterials.length > 0
    ? snapshotMaterials.map((item) => ({ id: item.id, filename: item.filename || t('unnamedSource') }))
    : materials.map((item) => ({ id: item.id, filename: item.filename }))

  return (
    <div className="modeling-workbench">
      <div className={`status-strip${modelReady ? '' : ' blocked'}`}>
        <p>{modelReady ? t('serviceReady') : t('serviceBlocked')}</p>
        {!modelReady && missingKeys.length > 0 ? (
          <p className="muted">{t('missingModelKeys')}: {missingKeys.join(', ')}</p>
        ) : null}
        <p className="muted">
          {readiness.live_azure_possible ? t('liveAzureReady') : t('azureBlockedBody')}
        </p>
      </div>

      <div className="modeling-toolbar">
        <button
          className="btn btn-primary"
          type="button"
          disabled={!canStart}
          onClick={() => void onStart()}
        >
          {busy && !pending ? t('startingRun') : latestRun && (latestRun.status === 'failed' || latestRun.status === 'cancelled') ? t('newRun') : t('startModeling')}
        </button>
        {latestRun && ACTIVE.has(latestRun.status) ? (
          <button className="btn btn-ghost" type="button" disabled={cancelling} onClick={() => void onCancel()}>
            {cancelling ? t('canceling') : t('cancelRun')}
          </button>
        ) : null}
        {latestRun ? (
          <span className="muted">
            {t('runIdLabel')} {latestRun.id.slice(0, 8)} · {runStatusLabel(latestRun.status, t)} · {t('lastUpdated')} {latestRun.updated_at}
            {latestRun.stale_input ? ` · stale_input` : ''}
            {latestRun.error_message ? ` — ${latestRun.error_message}` : ''}
          </span>
        ) : null}
      </div>
      {error ? <p role="alert">{error}</p> : null}

      {latestRun?.status === 'waiting_for_user' || pending ? (
        <section className="composer" aria-label={t('clarification')}>
          <h2>{t('clarification')}</h2>
          <p>{t('waitingForClarificationBody')}</p>
          {pending ? <p><strong>{pending.question}</strong></p> : null}
          {pending?.reason ? <p className="muted">{pending.reason}</p> : null}
          <label className="field">
            <span>{t('answerClarification')}</span>
            <textarea value={answer} onChange={(event) => setAnswer(event.target.value)} rows={4} />
          </label>
          <button className="btn btn-primary" type="button" disabled={busy || !answer.trim()} onClick={() => void onResume()}>
            {busy ? t('answering') : t('submitAnswer')}
          </button>
        </section>
      ) : null}

      <div className="modeling-tabs" role="tablist">
        {(['sources', 'claims', 'activity'] as const).map((id) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={pane === id}
            className={pane === id ? 'active' : ''}
            onClick={() => setPane(id)}
          >
            {id === 'sources' ? t('materials') : id === 'claims' ? t('claims') : t('activity')}
          </button>
        ))}
      </div>

      <div className={`modeling-panes pane-${pane}`}>
        <aside className="modeling-sources">
          <h2>{t('materials')}</h2>
          <ul className="source-list">
            {sourceList.map((material) => {
              const coverage = latestRun?.coverage.find((item) => item.material_id === material.id)
              const count = claims.filter((claim) => claim.evidence_refs.some((ref) => ref.material_id === material.id)).length
              return (
                <li key={material.id}>
                  <button
                    type="button"
                    className={material.id === selectedId ? 'active' : ''}
                    onClick={() => {
                      setSelectedId(material.id)
                      setPane('sources')
                    }}
                  >
                    <strong>{material.filename}</strong>
                    <span className="muted">
                      {coverage ? coverageLabel(coverage.state, t) : ''}
                      {count ? ` · ${count}` : ''}
                    </span>
                  </button>
                </li>
              )
            })}
          </ul>
          <SourceViewer
            key={`${snapshotRunId ?? 'live'}-${selected?.id ?? 'none'}`}
            projectId={projectId}
            material={selected}
            spans={selectedSpans}
            highlight={highlight}
            runId={snapshotRunId}
          />
          <h3>{t('relatedClaims')}</h3>
          {related.length === 0 ? (
            <p className="muted">{t('noRelatedClaims')}</p>
          ) : (
            <ul className="source-list">
              {related.map((claim) => (
                <li key={claim.id}>
                  <button
                    type="button"
                    className={claim.id === focusClaimId ? 'active' : ''}
                    onClick={() => {
                      setFocusClaimId(claim.id)
                      setPane('claims')
                    }}
                  >
                    <strong>{claimKindHeading(claim.claim_kind, t)}</strong>
                    <span className="muted">{claim.original_statement}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>

        <section className="modeling-claims">
          <h2>{t('claims')}</h2>
          {!latestDraft ? (
            <EmptyState
              title={runInFlight ? t('draftInProgress') : t('noDraft')}
              body={runInFlight ? t('draftInProgressBody') : latestRun ? t('runHasNoDraftBody') : t('noDraftBody')}
            />
          ) : (
            <div className="stack">
              {grouped.map((group) => (
                <div key={group.kind} className="claim-group">
                  <h3>{group.kind === 'constraint' ? t('constraintsSection')
                    : group.kind === 'objective' ? t('objectivesSection')
                      : group.kind === 'unknown' ? t('unknownsSection')
                        : group.kind === 'conflict' ? t('conflictsSection')
                          : group.kind === 'parameter' ? t('parametersSection')
                            : group.kind === 'assumption' ? t('assumptionsSection')
                              : group.kind === 'variable' ? t('variablesSection')
                                : group.kind === 'readiness' ? t('readinessSection')
                                  : t('entitiesSection')}</h3>
                  {group.items.map((claim) => (
                    <article className={`fact ${claim.review_status}${claim.id === focusClaimId ? ' selected-source' : ''}`} key={claim.id}>
                      <div className="fact-label">{claimKindHeading(claim.claim_kind, t)} · {reviewLabel(claim.review_status, t)}</div>
                      <p><strong>{t('originalStatement')}</strong> {claim.original_statement}</p>
                      {claim.proposed_interpretation ? (
                        <p className="muted"><strong>{t('interpretation')}</strong> {claim.proposed_interpretation}</p>
                      ) : null}
                      {claim.edited_statement ? (
                        <p><strong>{t('editedStatement')}</strong> {claim.edited_statement}</p>
                      ) : null}
                      {claim.evidence_refs.length > 0 ? (
                        <p className="muted">
                          {t('sourceLinks')}:{' '}
                          {claim.evidence_refs.map((ref, index) => (
                            <button
                              key={`${claim.id}-${ref.material_id}-${index}`}
                              type="button"
                              className="btn btn-ghost"
                              onClick={() => {
                                setSelectedId(ref.material_id)
                                setFocusClaimId(claim.id)
                                setPane('sources')
                              }}
                            >
                              {sourceRefLabel(ref, materials, t)}
                            </button>
                          ))}
                        </p>
                      ) : null}
                      {editId === claim.id ? (
                        <label className="field">
                          <span>{t('editClaim')}</span>
                          <textarea value={editText} onChange={(event) => setEditText(event.target.value)} rows={3} />
                          <button className="btn btn-secondary" type="button" onClick={() => void onReview(claim, 'accepted', editText)}>
                            {t('saveEdit')}
                          </button>
                        </label>
                      ) : (
                        <div className="review-actions">
                          <button className="btn btn-secondary" type="button" disabled={busy || !canMutateDraft} onClick={() => void onReview(claim, 'accepted')}>{t('reviewAccept')}</button>
                          <button className="btn btn-secondary" type="button" disabled={busy || !canMutateDraft} onClick={() => void onReview(claim, 'rejected')}>{t('reviewReject')}</button>
                          <button className="btn btn-secondary" type="button" disabled={busy || !canMutateDraft} onClick={() => void onReview(claim, 'not_applicable')}>{t('reviewNA')}</button>
                          <button className="btn btn-ghost" type="button" disabled={busy || !canMutateDraft} onClick={() => { setEditId(claim.id); setEditText(claim.edited_statement || claim.proposed_interpretation || claim.original_statement) }}>{t('editClaim')}</button>
                          <button className="btn btn-ghost" type="button" onClick={() => void onHistory(claim.id)}>{t('reviewHistory')}</button>
                        </div>
                      )}
                      {historyId === claim.id && historyError ? <p role="alert">{historyError}</p> : null}
                      {historyId === claim.id && history.length > 0 ? (
                        <ol className="activity-log">
                          {history.map((event) => (
                            <li key={event.id}>
                              {event.previous_status} → {event.new_status}
                              {event.new_edited_statement ? ` · ${event.new_edited_statement}` : ''}
                            </li>
                          ))}
                        </ol>
                      ) : null}
                    </article>
                  ))}
                </div>
              ))}
              <p className="muted">{t('freezeNeedsReview')}</p>
              <button className="btn btn-primary" type="button" disabled={busy || !canMutateDraft} onClick={() => void onFreeze()}>
                {busy ? t('freezing') : t('freezeBaseline')}
              </button>
            </div>
          )}
        </section>

        <aside className="modeling-activity">
          <h2>{t('activity')}</h2>
          <h3>{t('coverage')}</h3>
          <ul className="coverage-list">
            {(latestRun?.coverage ?? []).map((item) => (
              <li key={item.material_id}>
                {item.filename ?? t('unnamedSource')}: {coverageLabel(item.state, t)}
              </li>
            ))}
          </ul>
          <ol className="activity-log">
            {(latestRun?.events ?? []).slice(-12).map((event) => (
              <li key={event.id}>
                <strong>{event.title}</strong>
                {event.detail ? <span className="muted"> {event.detail}</span> : null}
              </li>
            ))}
          </ol>
        </aside>
      </div>
    </div>
  )
}
