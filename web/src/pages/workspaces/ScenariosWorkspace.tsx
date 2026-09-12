import { RuleList, VersionMark } from '../../components/RuleList'
import { EmptyState } from '../../components/EmptyState'
import { NullValue, Quantity } from '../../components/NullValue'
import type { Scenario, ScenarioRevision } from '../../api/types'
import { useI18n } from '../../i18n'
import { formatTimestamp, shortId } from '../../lib/format'

type ScenariosWorkspaceProps = { scenarios: Scenario[]; latestScenarioId: string | null; latestRevisionId: string | null }

export function ScenariosWorkspace({ scenarios, latestScenarioId, latestRevisionId }: ScenariosWorkspaceProps) {
  const { t } = useI18n()
  if (scenarios.length === 0) {
    return (
      <div className="stage">
        <div className="notice honest">{t('noScenariosNotice')}</div>
        <EmptyState title={t('noScenarios')} body={t('noScenariosBody')} />
      </div>
    )
  }
  return (
    <div className="stage">
      <div className="notice honest">{t('scenariosNotice')}</div>
      <div className="stack">
        {scenarios.map((scenario) => (
          <ScenarioCard key={scenario.id} scenario={scenario} isLiveHead={scenario.id === latestScenarioId} latestRevisionId={latestRevisionId} />
        ))}
      </div>
    </div>
  )
}

function ScenarioCard({ scenario, isLiveHead, latestRevisionId }: { scenario: Scenario; isLiveHead: boolean; latestRevisionId: string | null }) {
  const { locale, t } = useI18n()
  const confirmed = scenario.revisions.some((item) => item.version_state === 'confirmed')
  return (
    <article className={confirmed ? 'fact confirmed' : 'fact draft'}>
      <div className="fact-label">
        {confirmed ? t('confirmedBaseline') : t('hypothetical')}{isLiveHead ? ` · ${t('liveHead')}` : ''}
      </div>
      <h3>{scenario.name}</h3>
      <div className="meta-row">
        <span>{t('id')} {shortId(scenario.id)}</span>
        <span>{scenario.revisions.length} {t('revisions')}</span>
        <span>{t('opened')} {formatTimestamp(scenario.created_at, locale, t)}</span>
      </div>
      <div className="lineage" style={{ marginTop: 12 }}>
        {scenario.revisions.map((revision) => <RevisionBlock key={revision.id} revision={revision} isLatest={revision.id === latestRevisionId} />)}
      </div>
    </article>
  )
}

function RevisionBlock({ revision, isLatest }: { revision: ScenarioRevision; isLatest: boolean }) {
  const { locale, t } = useI18n()
  const model = revision.formal_model
  return (
    <div className={`lineage-item${isLatest ? ' is-latest' : ''}`}>
      <div className="revision-no">v{revision.revision_no}</div>
      <div>
        <VersionMark state={revision.version_state} />
        {revision.notes ? <p>{revision.notes}</p> : null}
        <div className="meta-row">
          <span>{shortId(revision.id)}</span>
          <span>{t('basedOnUnderstanding')} {revision.based_on_understanding_id ? shortId(revision.based_on_understanding_id) : t('none')}</span>
          <span>{formatTimestamp(revision.created_at, locale, t)}</span>
        </div>
        {model ? (
          <div className="fact" style={{ marginTop: 10 }}>
            <div className="fact-label">{t('formalModelMetadata')}</div>
            <h3>{model.name}</h3>
            <div className="meta-row">
              <VersionMark state={model.version_state} />
              <Quantity name={t('variables')} value={model.variable_count} />
              <Quantity name={t('constraints')} value={model.constraint_count} />
              <span>{t('objective')} {model.objective_text ? model.objective_text : <NullValue />}</span>
            </div>
            {model.notes ? <p className="muted" style={{ marginTop: 8 }}>{model.notes}</p> : null}
          </div>
        ) : <p className="muted" style={{ marginTop: 8 }}>{t('noFormalModel')}</p>}
        <div style={{ marginTop: 12 }}><RuleList rules={revision.rules} /></div>
      </div>
    </div>
  )
}
