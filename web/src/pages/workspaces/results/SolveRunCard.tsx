import { useState } from 'react'
import { errorMessage, resumeSolveRun } from '../../../api/client'
import type { SolveRun } from '../../../api/types'
import { NullValue, Quantity } from '../../../components/NullValue'
import { useI18n } from '../../../i18n'
import { formatTimestamp, solveRunStateLabel } from '../../../lib/format'

export function SolveRunCard({ run, projectId, revisionNo, reload }: { run: SolveRun; projectId: string; revisionNo?: number; reload: () => Promise<void> | void }) {
  const { locale, t } = useI18n()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  async function resume() {
    setBusy(true); setError(null)
    try { await resumeSolveRun(projectId, run.id); await reload() }
    catch (err) { setError(errorMessage(err)) }
    finally { setBusy(false) }
  }
  const firstCandidate = run.candidates[0]
  const details = firstCandidate?.details
  const explanation = run.explanation ?? firstCandidate?.explanation ?? (details?.explanation as SolveRun['explanation'] | undefined)
  const explanationRecord = explanation as Record<string, unknown> | undefined
  const conflicts = Array.isArray(explanationRecord?.conflicts) ? explanationRecord.conflicts as Array<Record<string, unknown>> : []
  const issues = Array.isArray(explanationRecord?.issues) ? explanationRecord.issues : []
  const summary = typeof explanationRecord?.summary === 'string' ? explanationRecord.summary : run.message ?? '—'
  const executed = run.execution !== 'not_executed' && run.run_state !== 'pending'
  return <article className={`fact ${run.run_state === 'optimal' || run.run_state === 'feasible' ? 'confirmed' : run.run_state === 'infeasible' || run.run_state === 'model_invalid' ? 'conflicted' : 'unknown'}`}><div className="fact-label">{executed ? t('solveResult') : t('solveNotRun')}</div><h3>{solveRunStateLabel(run.run_state, t)}{revisionNo ? ` · v${revisionNo}` : ''}</h3><div className="meta-row"><span>{t('solver')}: {run.solver_name ?? <NullValue />}</span><span>{t('execution')}: {run.execution}</span><span>{t('started')}: {run.started_at ? formatTimestamp(run.started_at, locale, t) : <NullValue />}</span><span>{t('finished')}: {run.finished_at ? formatTimestamp(run.finished_at, locale, t) : <NullValue />}</span></div>{run.message ? <p className="muted">{run.message}</p> : null}{!executed ? <p className="muted">{t('solveNotRunBody')}</p> : null}<div className="review-actions"><a className="btn btn-secondary" href={`/api/projects/${projectId}/solve-runs/${run.id}/export.json`} download>{t('exportJson')}</a><a className="btn btn-secondary" href={`/api/projects/${projectId}/solve-runs/${run.id}/export.md`} download>{t('exportMarkdown')}</a>{run.run_state === 'pending' || run.run_state === 'running' ? <button className="btn btn-secondary" type="button" disabled={busy} onClick={() => void resume()}>{busy ? t('resumingSolve') : t('resumeSolve')}</button> : null}</div>{error ? <p role="alert">{error}</p> : null}<details className="tech-details"><summary>{t('technicalDetails')}</summary><p>{t('revisionState')}: {run.scenario_revision_id}</p><p>{t('inputFingerprint')}: {run.input_fingerprint ?? '—'}</p><p>{t('heartbeat')}: {run.heartbeat_at ?? '—'}</p><p>{t('recoveryCount')}: {run.resume_count ?? 0}</p></details>{executed && run.candidates.length ? <div className="stack" style={{ marginTop: 12 }}>{run.candidates.map((candidate, index) => <CandidateCard key={candidate.id} candidate={candidate} index={index} />)}</div> : <p className="muted">{t('noCandidates')}</p>}{explanation ? <div className="explanation"><strong>{t('solverExplanation')}</strong><p>{summary}</p>{issues.length || conflicts.length ? <ul className="issue-list">{[...issues.map(String), ...conflicts.map((conflict) => String(conflict.message ?? conflict.constraint_key ?? JSON.stringify(conflict)))].map((item, index) => <li key={index}>{item}</li>)}</ul> : null}</div> : null}</article>
}

function CandidateCard({ candidate, index }: { candidate: SolveRun['candidates'][number]; index: number }) {
  const { t } = useI18n()
  const assignments = Array.isArray(candidate.details?.assignments) ? candidate.details.assignments as Array<Record<string, unknown>> : []
  return <div className="fact present"><div className="fact-label">{t('candidate')} {index + 1}</div><h3>{candidate.label ?? t('unnamedCandidate')}</h3><div className="meta-row"><Quantity name={t('objective')} value={candidate.objective_value} /><span>{t('selected')}: {candidate.is_selected == null ? <NullValue /> : String(candidate.is_selected)}</span></div>{assignments.length ? <ScheduleTable assignments={assignments} /> : null}<PortfolioCandidateSummary result={candidate.result} />{candidate.notes ? <p className="muted">{candidate.notes}</p> : null}<ProvenanceSummary provenance={candidate.provenance ?? candidate.details?.provenance} /></div>
}

function PortfolioCandidateSummary({ result }: { result?: Record<string, unknown> | null }) {
  const { t } = useI18n()
  if (!result || !Array.isArray(result.selected_items)) return null
  const selected = result.selected_items as Array<Record<string, unknown>>
  return <div className="meta-row"><span>{t('selectedItems')}: {selected.map((item) => String(item.name ?? item.key ?? '—')).join(', ') || '—'}</span><Quantity name={t('portfolioValue')} value={typeof result.value === 'number' ? result.value : null} /><Quantity name={t('portfolioCost')} value={typeof result.cost === 'number' ? result.cost : null} /></div>
}

function ProvenanceSummary({ provenance }: { provenance: unknown }) {
  const { t } = useI18n()
  if (!provenance || typeof provenance !== 'object') return null
  const sourceClaims = (provenance as { source_claims?: unknown }).source_claims
  if (!sourceClaims || typeof sourceClaims !== 'object') return null
  const claims = sourceClaims as Record<string, unknown>
  const keys = Object.keys(claims)
  return <details className="tech-details"><summary>{t('resultProvenance')} ({keys.length})</summary><p className="muted">{t('resultProvenanceBody')}</p><ul className="issue-list provenance-list">{keys.slice(0, 12).map((key) => { const refs = Array.isArray(claims[key]) ? claims[key] as Array<Record<string, unknown>> : []; const materials = [...new Set(refs.map((ref) => String(ref.material_id ?? '')).filter(Boolean))]; return <li key={key}><code>{key}</code> · {refs.length} {t('evidenceRefs')}{materials.length ? ` · ${materials.join(', ')}` : ''}</li> })}</ul></details>
}

function ScheduleTable({ assignments }: { assignments: Array<Record<string, unknown>> }) {
  const { t } = useI18n()
  return <div className="schedule-table" role="table" aria-label={t('scheduleAssignments')}><div className="schedule-row schedule-head" role="row"><span>{t('session')}</span><span>{t('timeSlot')}</span><span>{t('room')}</span><span>{t('instructor')}</span></div>{assignments.map((item, index) => <div className="schedule-row" role="row" key={String(item.session_key ?? index)}><span>{String(item.session_name ?? item.session_key ?? '—')}</span><span>{String(item.slot_label ?? item.slot_key ?? '—')}</span><span>{String(item.room_name ?? item.room_key ?? '—')}</span><span>{String(item.instructor_name ?? item.instructor_key ?? '—')}</span></div>)}</div>
}

