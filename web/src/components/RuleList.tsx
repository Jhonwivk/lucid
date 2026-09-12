import type { EvidenceStatus, PremiseStatus, ReviewStatus, Rule, VersionState } from '../api/types'
import { useI18n } from '../i18n'
import { conditionKindLabel, evidenceLabel, premiseLabel, reviewLabel, ruleKindLabel, versionLabel } from '../lib/format'
import { Quantity } from './NullValue'

function factTone(evidence: EvidenceStatus, review: ReviewStatus): string {
  if (evidence === 'conflicted' || review === 'rejected') return 'conflicted'
  if (evidence === 'missing' || evidence === 'unknown') return 'unknown'
  if (review === 'accepted' && evidence === 'present') return 'accepted'
  return 'draft'
}

export function RuleList({ rules }: { rules: Rule[] }) {
  const { t } = useI18n()
  if (rules.length === 0) return <p className="muted">{t('noRules')}</p>
  return (
    <div className="stack">
      {rules.map((rule) => (
        <article className={`fact ${factTone(rule.evidence_status, rule.review_status)}`} key={rule.id}>
          <div className="fact-label">{ruleKindLabel(rule.rule_kind, t)} {t('rule')}</div>
          <h3>{rule.statement}</h3>
          <div className="meta-row">
            <span>{reviewLabel(rule.review_status, t)}</span>
            <span>{evidenceLabel(rule.evidence_status, t)}</span>
            {rule.condition_kind ? <span>{t('condition')} {conditionKindLabel(rule.condition_kind, t)}</span> : null}
            {rule.premise_status ? <span>{premiseLabel(rule.premise_status as PremiseStatus, t)}</span> : null}
            <Quantity name={t('cost')} value={rule.cost} />
            <Quantity name={t('capacity')} value={rule.capacity} />
            <Quantity name={t('permission')} value={rule.permission} />
          </div>
          {rule.premise_text ? <p className="muted" style={{ marginTop: 8 }}>{rule.premise_text}</p> : null}
        </article>
      ))}
    </div>
  )
}

export function VersionMark({ state }: { state: VersionState }) {
  const { t } = useI18n()
  const tone = state === 'confirmed' ? 'confirmed' : state === 'invalidated' ? 'conflicted' : state === 'draft' ? 'draft' : 'unknown'
  return <span className={`fact-label ${tone}`}>{versionLabel(state, t)}</span>
}
