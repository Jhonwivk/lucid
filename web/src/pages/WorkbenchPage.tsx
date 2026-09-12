import { Link, Navigate, useParams } from 'react-router-dom'
import { BrandMark } from '../components/BrandMark'
import { ErrorState } from '../components/ErrorState'
import { LanguageToggle } from '../components/LanguageToggle'
import { LoadingState } from '../components/LoadingState'
import { StatusPill } from '../components/StatusPill'
import { useHealth } from '../hooks/useHealth'
import { useWorkbench } from '../hooks/useWorkbench'
import { useI18n } from '../i18n'
import { formatTimestamp, isTemplateProject, maturityLabel } from '../lib/format'
import { WORKSPACE_ALIASES, WORKSPACE_IDS, type WorkspaceId } from '../api/types'
import { MaterialsWorkspace } from './workspaces/MaterialsWorkspace'
import { ModelingWorkspace } from './workspaces/ModelingWorkspace'
import { BaselineWorkspace } from './workspaces/BaselineWorkspace'
import { ResultsWorkspace } from './workspaces/ResultsWorkspace'

function resolveWorkspace(value: string | undefined): WorkspaceId | 'redirect' | null {
  if (!value) return null
  if (WORKSPACE_ALIASES[value]) return 'redirect'
  if (WORKSPACE_IDS.includes(value as WorkspaceId)) return value as WorkspaceId
  return null
}

export function WorkbenchPage() {
  const { projectId, workspaceId } = useParams()
  const { locale, t } = useI18n()
  const health = useHealth()
  const { state, data, error, reload } = useWorkbench(projectId)

  if (!projectId) return <Navigate to="/analyses" replace />
  if (workspaceId && WORKSPACE_ALIASES[workspaceId]) {
    return <Navigate to={`/analyses/${projectId}/${WORKSPACE_ALIASES[workspaceId]}`} replace />
  }
  const current = resolveWorkspace(workspaceId)
  if (!current || current === 'redirect') {
    return <Navigate to={`/analyses/${projectId}/materials`} replace />
  }

  const labels: Record<WorkspaceId, string> = {
    materials: t('materials'),
    modeling: t('modeling'),
    baseline: t('baseline'),
    results: t('results'),
  }
  const showing = data && data.project.id === projectId ? data : null
  const viewState = showing ? 'ready' : state === 'error' ? 'error' : 'loading'

  return (
    <div className="page">
      <div className="shell">
        <header className="topbar">
          <BrandMark subtle={t('workbench')} to="/analyses" />
          <div className="topbar-meta">
            <LanguageToggle />
            <StatusPill
              state={health.state}
              label={
                health.state === 'ready'
                  ? `API ${health.health?.status ?? 'ok'}`
                  : health.state === 'loading'
                    ? t('apiConnecting')
                    : t('apiUnavailable')
              }
            />
          </div>
        </header>

        {viewState === 'loading' ? <LoadingState label={t('openingAnalysis')} rows={5} /> : null}
        {viewState === 'error' ? (
          <ErrorState
            title={t('analysisOpenError')}
            body={error ?? t('projectNotReturned')}
            action={<Link className="btn btn-secondary" to="/analyses">{t('backAnalyses')}</Link>}
          />
        ) : null}

        {viewState === 'ready' && showing ? (
          <>
            <div className="project-head">
              <div className="project-kicker">
                <Link className="crumb" to="/analyses">{t('myAnalyses')}</Link>
                <span>{maturityLabel(showing.project.workflow_maturity, t)}</span>
                <span>{t('updated')} {formatTimestamp(showing.project.updated_at, locale, t)}</span>
                {showing.project.is_demo ? <span className="stamp">{t('demoData')}</span> : null}
                {isTemplateProject(showing.project) ? (
                  <span className="stamp template-stamp">{t('templateFixture')}</span>
                ) : null}
              </div>
              <h1>{showing.project.title}</h1>
              {showing.project.decision_question ? <p className="lede">{showing.project.decision_question}</p> : null}
              {showing.project.summary && showing.project.summary !== showing.project.decision_question ? (
                <p className="muted">{showing.project.summary}</p>
              ) : null}
            </div>

            <nav className="workspace-nav" aria-label={t('analysisWorkspaces')}>
              {WORKSPACE_IDS.map((id) => (
                <Link
                  key={id}
                  className={`workspace-link${id === current ? ' active' : ''}`}
                  to={`/analyses/${projectId}/${id}`}
                >
                  {labels[id]}
                </Link>
              ))}
            </nav>

            <div className="workbench">
              <main className="work-main">
                {current === 'materials' ? (
                  <MaterialsWorkspace
                    projectId={projectId}
                    materials={showing.project.materials}
                    sourceSpans={showing.sourceSpans}
                    reload={reload}
                  />
                ) : null}
                {current === 'modeling' ? (
                  <ModelingWorkspace
                    projectId={projectId}
                    question={showing.project.decision_question || showing.project.summary || ''}
                    materials={showing.project.materials}
                    sourceSpans={showing.sourceSpans}
                    runs={showing.modelingRuns}
                    drafts={showing.drafts}
                    readiness={showing.readiness}
                    reload={reload}
                  />
                ) : null}
                {current === 'baseline' ? (
                  <BaselineWorkspace
                    projectId={projectId}
                    baselines={showing.baselines}
                    drafts={showing.drafts}
                    reload={reload}
                  />
                ) : null}
                {current === 'results' ? <ResultsWorkspace solveRuns={showing.solveRuns} /> : null}
              </main>
            </div>
          </>
        ) : null}
      </div>
    </div>
  )
}
