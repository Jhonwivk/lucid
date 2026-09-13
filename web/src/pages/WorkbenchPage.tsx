import { Link, Navigate, useParams } from 'react-router-dom'
import { BrandMark } from '../components/BrandMark'
import { HomeIcon } from '../components/HomeIcon'
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
import './AnalysesPage.css'

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
  const { state, data, error, stale, reload } = useWorkbench(projectId)

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
    <div className="page lu-home lu-workbench-page">
      <div className="shell">
        <header className="topbar lu-header">
          <BrandMark subtle={t('workbench')} to="/analyses" />
          <label className="lu-global-search lu-workbench-search">
            <HomeIcon name="search" />
            <input aria-label={t('searchPlaceholder')} placeholder={t('searchPlaceholder')} readOnly />
            <kbd>⌘ K</kbd>
          </label>
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
            <span className="lu-avatar" title={t('workbench')}>L</span>
          </div>
        </header>

        <nav className="lu-stages" aria-label={t('analysisWorkspaces')}>
          {WORKSPACE_IDS.map((id, index) => (
            <Link key={id} className={`lu-stage ${id === current ? 'is-current' : ''}`} to={`/analyses/${projectId}/${id}`}>
              <b>{index + 1}</b><span><strong>{labels[id]}</strong><small>{id[0].toUpperCase() + id.slice(1)}</small></span>
            </Link>
          ))}
        </nav>

        {viewState === 'loading' ? <LoadingState label={t('openingAnalysis')} rows={5} /> : null}
        {viewState === 'error' ? (
          <ErrorState
            title={t('analysisOpenError')}
            body={error ?? t('projectNotReturned')}
            action={
              <>
                <button className="btn btn-primary" type="button" onClick={() => void reload()}>{t('retry')}</button>
                <Link className="btn btn-secondary" to="/analyses">{t('backAnalyses')}</Link>
              </>
            }
          />
        ) : null}

        {viewState === 'ready' && showing ? (
          <div className="workspace-frame">
            <aside className="project-rail" aria-label={t('projectNavigation')}>
              <div className="rail-project">
                <span className="rail-overline">{t('currentProject')}</span>
                <strong>{showing.project.title}</strong>
                <span className="rail-status"><i />{t('ready')}</span>
              </div>
              <nav className="rail-nav">
                <Link className="rail-link" to={`/analyses/${projectId}/materials`}><span className="rail-icon icon-overview" aria-hidden="true" />{t('overview')}</Link>
                <Link className="rail-link active" to={`/analyses/${projectId}/results`}><span className="rail-icon icon-analysis" aria-hidden="true" />{t('analysis')}</Link>
                <Link className="rail-link" to={`/analyses/${projectId}/materials`}><span className="rail-icon icon-documents" aria-hidden="true" />{t('documents')}</Link>
                <Link className="rail-link" to="/analyses"><span className="rail-icon icon-settings" aria-hidden="true" />{t('settings')}</Link>
              </nav>
              <div className="rail-footer"><span>{t('lastSaved')}</span><strong>{formatTimestamp(showing.project.updated_at, locale, t)}</strong></div>
            </aside>
            <div className="workspace-content">
            {stale && error ? (
              <p className="notice warn" role="status">
                {t('staleReload')} {error}{' '}
                <button className="btn btn-ghost" type="button" onClick={() => void reload()}>{t('retry')}</button>
              </p>
            ) : null}
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
              <div className="lu-workspace-title"><span className="lu-step-badge">{WORKSPACE_IDS.indexOf(current) + 1}</span><h1>{labels[current]}</h1></div>
              <p className="lede lu-project-context"><strong>{showing.project.title}</strong>{showing.project.decision_question ? ` · ${showing.project.decision_question}` : showing.project.summary ? ` · ${showing.project.summary}` : ''}</p>
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
              <main className="work-main" key={projectId}>
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
                    runs={showing.modelingRuns}
                    scenarios={showing.scenarios}
                    currentBaselineId={showing.project.latest.baseline_id}
                    reload={reload}
                  />
                ) : null}
                {current === 'results' ? (
                  <ResultsWorkspace
                    key={showing.project.latest.scenario_revision_id ?? 'no-revision'}
                    projectId={projectId}
                    solveRuns={showing.solveRuns}
                    scenarios={showing.scenarios}
                    latestRevisionId={showing.project.latest.scenario_revision_id}
                    readiness={showing.readiness}
                    reload={reload}
                  />
                ) : null}
              </main>
            </div>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}
