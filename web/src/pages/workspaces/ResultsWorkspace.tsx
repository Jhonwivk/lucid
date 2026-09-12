import { useState } from 'react'
import { EmptyState } from '../../components/EmptyState'
import { NullValue } from '../../components/NullValue'
import { compareScenarioRevisions, createScenarioRevision, createWhatIfScenario, errorMessage, previewScenarioImpact, runPortfolioSolve, runTrainingScheduleSolve } from '../../api/client'
import type { ReadinessPayload, Scenario, SolveRun } from '../../api/types'
import { useI18n } from '../../i18n'
import { SolveRunCard } from './results/SolveRunCard'

type ResultsWorkspaceProps = {
  projectId: string
  solveRuns: SolveRun[]
  scenarios: Scenario[]
  latestRevisionId: string | null
  readiness: ReadinessPayload
  reload: () => Promise<void> | void
}

export function ResultsWorkspace({ projectId, solveRuns, scenarios, latestRevisionId, readiness, reload }: ResultsWorkspaceProps) {
  const { t } = useI18n()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [maxCandidates, setMaxCandidates] = useState(3)
  const [collection, setCollection] = useState('constraints')
  const [changeKey, setChangeKey] = useState('')
  const [changeValue, setChangeValue] = useState('')
  const [impact, setImpact] = useState<Record<string, unknown> | null>(null)
  const [impactBusy, setImpactBusy] = useState(false)
  const [whatIfBusy, setWhatIfBusy] = useState(false)
  const [comparison, setComparison] = useState<Record<string, unknown> | null>(null)
  const [comparisonBusy, setComparisonBusy] = useState(false)
  const [scheduleJson, setScheduleJson] = useState('')
  const [scheduleBusy, setScheduleBusy] = useState(false)
  const [portfolioJson, setPortfolioJson] = useState('')
  const [portfolioBusy, setPortfolioBusy] = useState(false)
  const latest = (() => {
    for (const scenario of scenarios) {
      const revision = scenario.revisions.find((item) => item.id === latestRevisionId)
      if (revision) return { scenario, revision }
    }
    const scenario = scenarios[0]
    return scenario ? { scenario, revision: scenario.revisions[scenario.revisions.length - 1] } : null
  })()
  const revisionRuns = solveRuns.filter((run) => run.scenario_revision_id === latest?.revision.id).sort((a, b) => b.created_at.localeCompare(a.created_at))
  const latestRun = revisionRuns[0]
  const latestModel = latest?.revision.formal_model
  const solverReady = Boolean(latest?.revision.id && latestModel?.validation?.valid && latestModel.definition?.training_schedule)
  const portfolioReady = Boolean(latest?.revision.id && latestModel?.validation?.valid && latestModel.definition?.portfolio)

  async function runSolver() {
    if (!latest?.revision.id || busy) return
    setBusy(true); setError(null)
    try {
      await runTrainingScheduleSolve(projectId, { scenario_revision_id: latest.revision.id, formal_model_id: latestModel?.id, max_candidates: maxCandidates })
      await reload()
    } catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }
  async function saveTrainingModel() {
    if (!latest || !latestModel || scheduleBusy) return
    setScheduleBusy(true); setError(null)
    try {
      const trainingSchedule = JSON.parse(scheduleJson) as Record<string, unknown>
      for (const key of ['sessions', 'time_slots', 'rooms', 'instructors']) {
        if (!Array.isArray(trainingSchedule[key])) throw new Error(`${key} must be an array`)
      }
      const baseDefinition = latestModel.definition ?? { schema_version: 1, family: 'training_schedule', variables: [], parameters: [], constraints: [], objectives: [] }
      const variables = baseDefinition.variables.length ? baseDefinition.variables : [{ key: 'assignments', name: 'Session assignments', domain: 'session × slot × room × instructor' }]
      const constraints = baseDefinition.constraints.length ? baseDefinition.constraints : [
        { key: 'room_capacity', expression: 'room capacity >= attendees', strength: 'hard' as const, enabled: true, binding: 'room_capacity' as const },
        { key: 'room_availability', expression: 'room available for slot', strength: 'hard' as const, enabled: true, binding: 'room_availability' as const },
        { key: 'instructor_availability', expression: 'instructor available for slot', strength: 'hard' as const, enabled: true, binding: 'instructor_availability' as const },
        { key: 'instructor_skill', expression: 'instructor has required skill', strength: 'hard' as const, enabled: true, binding: 'instructor_skill' as const },
        { key: 'no_overlap', expression: 'room and instructor do not overlap', strength: 'hard' as const, enabled: true, binding: 'no_overlap' as const },
        { key: 'daily_instructor_load', expression: 'instructor daily load <= max', strength: 'hard' as const, enabled: true, binding: 'daily_instructor_load' as const },
      ]
      const objectives = baseDefinition.objectives.length ? baseDefinition.objectives : [{ key: 'preferred_day', expression: 'minimize preferred day misses', direction: 'minimize' as const, priority: 1, binding: 'preferred_day' as const }]
      await createScenarioRevision(latest.scenario.id, {
        version_state: 'confirmed',
        notes: 'Added the explicit training-schedule input required by the deterministic solver.',
        expected_parent_revision_id: latest.revision.id,
        formal_model: {
          name: latestModel.name,
          version_state: 'confirmed',
          variable_count: latestModel.variable_count,
          constraint_count: latestModel.constraint_count,
          objective_text: latestModel.objective_text,
          notes: latestModel.notes,
          dependency_fingerprint: latestModel.dependency_fingerprint,
          definition: { ...baseDefinition, family: 'training_schedule', variables, constraints, objectives, training_schedule: trainingSchedule },
        },
        rules: latest.revision.rules.map((rule) => ({
          rule_kind: rule.rule_kind,
          statement: rule.statement,
          review_status: rule.review_status,
          evidence_status: rule.evidence_status,
          source_span_id: rule.source_span_id,
          condition_kind: rule.condition_kind,
          premise_status: rule.premise_status,
          premise_text: rule.premise_text,
          cost: rule.cost,
          capacity: rule.capacity,
          permission: rule.permission,
        })),
      })
      setScheduleJson(''); await reload()
    } catch (err) { setError(err instanceof SyntaxError ? 'Training schedule JSON is invalid.' : errorMessage(err)) } finally { setScheduleBusy(false) }
  }
  function changePayload() {
    let value: unknown = changeValue
    try { value = JSON.parse(changeValue) } catch { /* expressions may be plain strings */ }
    if (value === null || typeof value !== 'object' || Array.isArray(value)) value = { value }
    return [{ collection, key: changeKey.trim(), operation: 'upsert', value }]
  }
  async function previewImpact() {
    if (!latest || !changeKey.trim() || impactBusy) return
    setImpactBusy(true); setError(null)
    try { setImpact(await previewScenarioImpact(latest.scenario.id, { base_revision_id: latest.revision.id, changes: changePayload() })) } catch (err) { setError(errorMessage(err)) } finally { setImpactBusy(false) }
  }
  async function commitWhatIf() {
    if (!latest || !changeKey.trim() || whatIfBusy) return
    setWhatIfBusy(true); setError(null)
    try {
      await createWhatIfScenario(latest.scenario.id, { name: `${latest.scenario.name} · what-if`, notes: 'Created from the visual what-if editor.', expected_parent_revision_id: latest.revision.id, changes: changePayload() })
      setImpact(null); await reload()
    } catch (err) { setError(errorMessage(err)) } finally { setWhatIfBusy(false) }
  }
  async function compareRevisions(leftRevisionId: string, rightRevisionId: string) {
    if (!latest || !leftRevisionId || !rightRevisionId || leftRevisionId === rightRevisionId || comparisonBusy) return
    setComparisonBusy(true); setError(null)
    try { setComparison(await compareScenarioRevisions(latest.scenario.id, leftRevisionId, rightRevisionId)) } catch (err) { setError(errorMessage(err)) } finally { setComparisonBusy(false) }
  }
  async function savePortfolioModel() {
    if (!latest || !latestModel || portfolioBusy) return
    setPortfolioBusy(true); setError(null)
    try {
      const portfolio = JSON.parse(portfolioJson) as Record<string, unknown>
      if (typeof portfolio.budget !== 'number' || !Array.isArray(portfolio.items) || portfolio.items.length === 0) throw new Error('Portfolio requires a numeric budget and at least one item.')
      const baseDefinition = latestModel.definition ?? { schema_version: 1, family: 'portfolio', variables: [], parameters: [], constraints: [], objectives: [] }
      await createScenarioRevision(latest.scenario.id, {
        version_state: 'confirmed', notes: 'Confirmed portfolio model input for deterministic selection.', expected_parent_revision_id: latest.revision.id,
        formal_model: { name: latestModel.name, version_state: 'confirmed', variable_count: latestModel.variable_count, constraint_count: latestModel.constraint_count, objective_text: latestModel.objective_text, notes: latestModel.notes, dependency_fingerprint: latestModel.dependency_fingerprint, definition: { ...baseDefinition, family: 'portfolio', variables: baseDefinition.variables.length ? baseDefinition.variables : [{ key: 'selected_items', name: 'Selected portfolio items', domain: 'subset' }], constraints: baseDefinition.constraints.length ? baseDefinition.constraints : [{ key: 'budget', expression: 'sum(selected.cost) <= budget', strength: 'hard', enabled: true }], objectives: baseDefinition.objectives.length ? baseDefinition.objectives : [{ key: 'total_value', expression: 'maximize sum(selected.value)', direction: 'maximize', priority: 1 }], portfolio } },
        rules: latest.revision.rules.map((rule) => ({ rule_kind: rule.rule_kind, statement: rule.statement, review_status: rule.review_status, evidence_status: rule.evidence_status, source_span_id: rule.source_span_id, condition_kind: rule.condition_kind, premise_status: rule.premise_status, premise_text: rule.premise_text, cost: rule.cost, capacity: rule.capacity, permission: rule.permission })),
      })
      setPortfolioJson(''); await reload()
    } catch (err) { setError(err instanceof SyntaxError ? 'Portfolio JSON is invalid.' : errorMessage(err)) } finally { setPortfolioBusy(false) }
  }
  async function runPortfolio() {
    if (!latest?.revision.id || busy) return
    setBusy(true); setError(null)
    try { await runPortfolioSolve(projectId, { scenario_revision_id: latest.revision.id, formal_model_id: latestModel?.id, max_candidates: maxCandidates }); await reload() } catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }
  return (
    <div className="stage">
      <div className="notice honest"><h2>{t('modelToSolve')}</h2><p>{t('modelToSolveBody')}</p></div>
      {!latest ? <EmptyState title={t('noScenarioToSolve')} body={t('noScenarioToSolveBody')} /> : <>
        <article className="fact present solve-input-card">
          <div className="fact-label">{t('solverInput')}</div><h3>{latest.scenario.name} · v{latest.revision.revision_no}</h3>
          <div className="meta-row"><span>{t('formalModel')}: {latestModel?.name ?? <NullValue />}</span><span>{t('modelState')}: {latestModel?.validation?.valid ? t('formalModelReady') : t('formalModelNeedsReview')}</span><span>{t('revisionState')}: {latest.revision.version_state}</span></div>
          {!solverReady && !portfolioReady ? <p className="muted">{t('solverNeedsTrainingModel')}</p> : null}
          {!latestModel?.definition?.training_schedule ? <TrainingModelEditor value={scheduleJson} onChange={setScheduleJson} busy={scheduleBusy} onSave={() => void saveTrainingModel()} /> : null}
          {!latestModel?.definition?.portfolio ? <PortfolioModelEditor value={portfolioJson} onChange={setPortfolioJson} busy={portfolioBusy} onSave={() => void savePortfolioModel()} /> : null}
          <div className="inline-form"><label className="field compact-field"><span>{t('maxCandidates')}</span><input type="number" min={1} max={20} value={maxCandidates} onChange={(event) => setMaxCandidates(Math.max(1, Math.min(20, Number(event.target.value) || 1)))} /></label><button className="btn btn-primary" type="button" disabled={!solverReady || busy || !readiness.solver} onClick={() => void runSolver()}>{busy ? t('solving') : t('runDeterministicSolver')}</button></div>
          {!readiness.solver ? <p className="muted">{t('solverUnavailable')}</p> : null}{error ? <p className="muted" role="alert">{error}</p> : null}
          {portfolioReady ? <button className="btn btn-secondary" type="button" disabled={busy || !readiness.solver} onClick={() => void runPortfolio()}>{busy ? t('solving') : t('runPortfolioSolver')}</button> : null}
        </article>
        {latestRun ? <SolveRunCard run={latestRun} projectId={projectId} revisionNo={latest.revision.revision_no} reload={reload} /> : <EmptyState title={t('noSolveRecords')} body={t('runSolverToSeeResults')} />}
        <WhatIfPanel scenario={latest.scenario} collection={collection} setCollection={setCollection} changeKey={changeKey} setChangeKey={setChangeKey} changeValue={changeValue} setChangeValue={setChangeValue} impact={impact} impactBusy={impactBusy} whatIfBusy={whatIfBusy} onPreview={() => void previewImpact()} onCommit={() => void commitWhatIf()} />
        <ComparisonPanel scenario={latest.scenario} comparison={comparison} busy={comparisonBusy} onCompare={compareRevisions} />
      </>}
      {solveRuns.length > 0 ? <details className="solve-history tech-details"><summary>{solveRuns.length} {t('solveHistoryAvailable')}</summary><div className="stack">{solveRuns.map((run) => <SolveRunCard key={run.id} run={run} projectId={projectId} revisionNo={scenarios.flatMap((scenario) => scenario.revisions).find((revision) => revision.id === run.scenario_revision_id)?.revision_no} reload={reload} />)}</div></details> : null}
    </div>
  )
}

function ComparisonPanel({ scenario, comparison, busy, onCompare }: { scenario: Scenario; comparison: Record<string, unknown> | null; busy: boolean; onCompare: (left: string, right: string) => Promise<void> }) {
  const { t } = useI18n()
  const revisions = scenario.revisions
  const [left, setLeft] = useState(revisions[0]?.id ?? '')
  const [right, setRight] = useState(revisions[1]?.id ?? '')
  if (revisions.length < 2) return null
  const list = (key: string) => Array.isArray(comparison?.[key]) ? comparison?.[key] as unknown[] : []
  return <article className="fact comparison-panel"><div className="fact-label">{t('scenarioComparison')}</div><h3>{t('compareRevisions')}</h3><div className="inline-form"><label className="field"><span>{t('leftRevision')}</span><select value={left} onChange={(event) => setLeft(event.target.value)}>{revisions.map((revision) => <option key={revision.id} value={revision.id}>v{revision.revision_no} · {revision.version_state}</option>)}</select></label><label className="field"><span>{t('rightRevision')}</span><select value={right} onChange={(event) => setRight(event.target.value)}>{revisions.map((revision) => <option key={revision.id} value={revision.id}>v{revision.revision_no} · {revision.version_state}</option>)}</select></label><button className="btn btn-secondary" type="button" disabled={busy || left === right} onClick={() => void onCompare(left, right)}>{busy ? t('comparing') : t('compare')}</button></div>{comparison ? <div className="comparison-result"><ComparisonList title={t('changedElements')} items={list('changed_elements')} /><ComparisonList title={t('changedRules')} items={list('changed_rules')} /><ComparisonList title={t('relatedSolveRuns')} items={list('solve_runs')} /></div> : <p className="muted">{t('comparePrompt')}</p>}</article>
}

function ComparisonList({ title, items }: { title: string; items: unknown[] }) {
  return <section className="comparison-list"><strong>{title}</strong>{items.length ? <ul>{items.map((item, index) => <li key={index}><code>{typeof item === 'string' ? item : JSON.stringify(item)}</code></li>)}</ul> : <p className="muted">—</p>}</section>
}

function TrainingModelEditor({ value, onChange, busy, onSave }: { value: string; onChange: (value: string) => void; busy: boolean; onSave: () => void }) {
  const { t } = useI18n()
  return <div className="training-editor"><div className="fact-label">{t('trainingModelEditor')}</div><p className="muted">{t('trainingModelEditorBody')}</p><textarea className="code-editor" value={value} onChange={(event) => onChange(event.target.value)} placeholder={JSON.stringify({ sessions: [{ key: 's1', name: 'Safety induction', duration_minutes: 60, attendees: 12, required_skill: 'safety', allowed_slot_keys: ['mon-0900'] }], time_slots: [{ key: 'mon-0900', day: 'Monday', start_minute: 540, end_minute: 600 }], rooms: [{ key: 'r1', name: 'Room 1', capacity: 20, available_slot_keys: ['mon-0900'] }], instructors: [{ key: 'i1', name: 'Instructor A', skills: ['safety'], available_slot_keys: ['mon-0900'], max_daily_sessions: 2 }] }, null, 2)} /><button className="btn btn-secondary" type="button" disabled={busy || !value.trim()} onClick={onSave}>{busy ? t('savingTrainingModel') : t('saveTrainingModel')}</button></div>
}

function PortfolioModelEditor({ value, onChange, busy, onSave }: { value: string; onChange: (value: string) => void; busy: boolean; onSave: () => void }) {
  const { t } = useI18n()
  const example = { budget: 100, items: [{ key: 'item-a', name: 'Pilot deployment', cost: 60, value: 90, required: false, conflict_keys: [] }, { key: 'item-b', name: 'Training package', cost: 50, value: 70, required: false, conflict_keys: ['item-a'] }] }
  return <div className="training-editor portfolio-editor"><div className="fact-label">{t('portfolioModelEditor')}</div><p className="muted">{t('portfolioModelEditorBody')}</p><textarea className="code-editor" value={value} onChange={(event) => onChange(event.target.value)} placeholder={JSON.stringify(example, null, 2)} /><button className="btn btn-secondary" type="button" disabled={busy || !value.trim()} onClick={onSave}>{busy ? t('savingPortfolioModel') : t('savePortfolioModel')}</button></div>
}

function WhatIfPanel(props: { scenario: Scenario; collection: string; setCollection: (value: string) => void; changeKey: string; setChangeKey: (value: string) => void; changeValue: string; setChangeValue: (value: string) => void; impact: Record<string, unknown> | null; impactBusy: boolean; whatIfBusy: boolean; onPreview: () => void; onCommit: () => void }) {
  const { t } = useI18n()
  return <article className="fact what-if-panel"><div className="fact-label">{t('whatIf')}</div><h3>{t('changeRuleAndPreview')}</h3><p className="muted">{t('whatIfBody')}</p><div className="inline-form"><label className="field"><span>{t('elementType')}</span><select value={props.collection} onChange={(event) => props.setCollection(event.target.value)}><option value="constraints">{t('constraints')}</option><option value="training_schedule">{t('trainingScheduleInputs')}</option><option value="parameters">{t('parametersSection')}</option><option value="variables">{t('variables')}</option><option value="objectives">{t('objectives')}</option></select></label><label className="field"><span>{t('elementKey')}</span><input value={props.changeKey} onChange={(event) => props.setChangeKey(event.target.value)} placeholder="rooms.atlas" /></label><label className="field"><span>{t('newValue')}</span><input value={props.changeValue} onChange={(event) => props.setChangeValue(event.target.value)} placeholder="JSON or expression" /></label></div><div className="review-actions"><button className="btn btn-secondary" type="button" disabled={props.impactBusy || !props.changeKey.trim()} onClick={props.onPreview}>{props.impactBusy ? t('previewing') : t('previewImpact')}</button><button className="btn btn-primary" type="button" disabled={props.whatIfBusy || !props.impact} onClick={props.onCommit}>{props.whatIfBusy ? t('creatingScenario') : t('createWhatIf')}</button></div>{props.impact ? <div className="impact-preview"><strong>{t('impactPreview')}</strong><pre>{JSON.stringify(props.impact, null, 2)}</pre></div> : null}</article>
}
