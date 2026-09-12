import { RuleList, VersionMark } from '../../components/RuleList'
import { EmptyState } from '../../components/EmptyState'
import type { Understanding } from '../../api/types'
import { useI18n } from '../../i18n'
import { formatTimestamp, shortId } from '../../lib/format'

type UnderstandingWorkspaceProps = { understandings: Understanding[]; latestId: string | null }

export function UnderstandingWorkspace({ understandings, latestId }: UnderstandingWorkspaceProps) {
  const { locale, t } = useI18n()
  if (understandings.length === 0) {
    return (
      <div className="stage">
        <div className="notice honest">{t('noUnderstandingNotice')}</div>
        <EmptyState title={t('noUnderstanding')} body={t('noUnderstandingBody')} />
      </div>
    )
  }

  const latest = understandings.find((item) => item.id === latestId) ?? understandings[understandings.length - 1]
  return (
    <div className="stage">
      <div className="notice honest">{t('understandingNotice')}</div>
      <section style={{ marginBottom: 28 }}>
        <p className="fact-label">{t('latestRevision')}</p>
        <h2 style={{ fontSize: '1.8rem', marginBottom: 8 }}>{t('understanding')} v{latest.revision_no}</h2>
        <div className="meta-row">
          <VersionMark state={latest.version_state} />
          <span>{t('id')} {shortId(latest.id)}</span>
          <span>{formatTimestamp(latest.created_at, locale, t)}</span>
          {latest.parent_revision_id ? <span>{t('parent')} {shortId(latest.parent_revision_id)}</span> : <span>{t('noParent')}</span>}
        </div>
        {latest.summary ? <p className="lede" style={{ marginTop: 12 }}>{latest.summary}</p> : null}
      </section>

      <div className="split-2" style={{ marginBottom: 24 }}>
        <FactGroup title={t('assumptions')} items={latest.assumptions} empty={t('noAssumptions')} tone="draft" />
        <FactGroup title={t('unknowns')} items={latest.unknowns} empty={t('noUnknowns')} tone="unknown" />
      </div>
      <FactGroup title={t('conflicts')} items={latest.conflicts} empty={t('noConflicts')} tone="conflicted" />

      <section style={{ marginTop: 28 }}>
        <h2 style={{ fontSize: '1.4rem', marginBottom: 12 }}>{t('rulesLatest')}</h2>
        <RuleList rules={latest.rules} />
      </section>

      <section style={{ marginTop: 32 }}>
        <h2 style={{ fontSize: '1.4rem', marginBottom: 8 }}>{t('versionHistory')}</h2>
        <p className="muted" style={{ marginBottom: 8 }}>{t('versionHistoryBody')}</p>
        <div className="lineage">
          {understandings.map((item) => (
            <div className={`lineage-item${item.id === latest.id ? ' is-latest' : ''}`} key={item.id}>
              <div className="revision-no">v{item.revision_no}</div>
              <div>
                <VersionMark state={item.version_state} />
                <p>{item.summary ?? t('noSummaryRevision')}</p>
                <div className="meta-row">
                  <span>{shortId(item.id)}</span>
                  <span>
                    {item.assumptions.length} {t('assumptionsCount')}, {item.unknowns.length} {t('unknownsCount')}, {item.conflicts.length} {t('conflictsCount')}, {item.rules.length} {t('rulesCount')}
                  </span>
                  <span>{formatTimestamp(item.created_at, locale, t)}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}

function FactGroup({ title, items, empty, tone }: { title: string; items: string[]; empty: string; tone: 'draft' | 'unknown' | 'conflicted' }) {
  return (
    <section>
      <h2 style={{ fontSize: '1.3rem', marginBottom: 10 }}>{title}</h2>
      {items.length === 0 ? <p className="muted">{empty}</p> : (
        <div className="stack">{items.map((item) => <div className={`fact ${tone}`} key={item}>{item}</div>)}</div>
      )}
    </section>
  )
}
