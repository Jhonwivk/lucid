import { EmptyState } from '../../components/EmptyState'
import { NullValue, Quantity } from '../../components/NullValue'
import type { SolveRun } from '../../api/types'
import { useI18n } from '../../i18n'
import { formatTimestamp, solveRunStateLabel } from '../../lib/format'

type ResultsWorkspaceProps = { solveRuns: SolveRun[] }

export function ResultsWorkspace({ solveRuns }: ResultsWorkspaceProps) {
  const { locale, t } = useI18n()
  return (
    <div className="stage">
      <div className="notice warn">
        <p className="stamp">{t('stage2Boundary')}</p>
        <h2>{t('solverNotImplemented')}</h2>
        <p>{t('solverNotImplementedBody')}</p>
        <p className="muted">{t('stage2BoundaryBody')}</p>
      </div>
      {solveRuns.length === 0 ? (
        <EmptyState title={t('noSolveRecords')} body={t('noSolveRecordsBody')} />
      ) : (
        <div className="stack">
          {solveRuns.map((run) => (
          <article className="fact unknown" key={run.id}>
            <div className="fact-label">{t('solveMetadata')}</div>
            <h3>{t('runState')} {solveRunStateLabel(run.run_state, t)}</h3>
            <p className="muted">{t('stage2BoundaryBody')}</p>
            <div className="meta-row">
              <span>{t('claimedExecution')} {String(run.claimed_execution)}</span>
              <span>{t('execution')} {run.execution}</span>
              <span>{t('solver')} {run.solver_name ? run.solver_name : <NullValue />}</span>
              <span>{t('started')} {run.started_at ? formatTimestamp(run.started_at, locale, t) : <NullValue />}</span>
              <span>{t('finished')} {run.finished_at ? formatTimestamp(run.finished_at, locale, t) : <NullValue />}</span>
            </div>
            {run.message ? <p className="muted" style={{ marginTop: 8 }}>{run.message}</p> : null}
            {run.candidates.length === 0 ? (
              <p className="muted" style={{ marginTop: 10 }}>{t('noCandidates')}</p>
            ) : (
              <div className="stack" style={{ marginTop: 12 }}>
                {run.candidates.map((candidate) => (
                  <div className="fact unknown" key={candidate.id}>
                    <div className="fact-label">{t('candidateMetadata')}</div>
                    <p>{candidate.label ?? t('unnamedCandidate')}</p>
                    <div className="meta-row">
                      <Quantity name={t('objective')} value={candidate.objective_value} />
                      <Quantity name={t('selected')} value={candidate.is_selected} />
                    </div>
                  </div>
                ))}
              </div>
            )}
            <details className="tech-details">
              <summary>{t('technicalDetails')}</summary>
              <p>{t('recorded')} {formatTimestamp(run.created_at, locale, t)}</p>
            </details>
          </article>
          ))}
        </div>
      )}
    </div>
  )
}
