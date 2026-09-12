import { useMemo, useState, type DragEvent, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { BrandMark } from '../components/BrandMark'
import { EmptyState } from '../components/EmptyState'
import { ErrorState } from '../components/ErrorState'
import { LanguageToggle } from '../components/LanguageToggle'
import { LoadingState } from '../components/LoadingState'
import { StatusPill } from '../components/StatusPill'
import { useHealth } from '../hooks/useHealth'
import { useProjects } from '../hooks/useProjects'
import { useTemplates } from '../hooks/useTemplates'
import { useI18n } from '../i18n'
import { importProjectMaterial, startAnalysis } from '../api/client'
import { formatTimestamp, isTemplateProject, latestCue, matchesQuery, maturityLabel } from '../lib/format'
import type { ProjectSummary, TemplateSummary } from '../api/types'

type OriginFilter = 'all' | 'mine' | 'demo' | 'template'

export function AnalysesPage() {
  const navigate = useNavigate()
  const { locale, t } = useI18n()
  const isZh = locale === 'zh-CN'
  const health = useHealth()
  const { state, projects, error, reload, seedDemo } = useProjects()
  const templates = useTemplates()
  const [query, setQuery] = useState('')
  const [origin, setOrigin] = useState<OriginFilter>('all')
  const [title, setTitle] = useState('')
  const [question, setQuestion] = useState('')
  const [pasted, setPasted] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [dragging, setDragging] = useState(false)
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const [seedError, setSeedError] = useState<string | null>(null)
  const [seeding, setSeeding] = useState(false)
  const [templateBusy, setTemplateBusy] = useState<string | null>(null)
  const [templateError, setTemplateError] = useState<string | null>(null)

  const visible = useMemo(() => {
    return projects.filter((project) => {
      const template = isTemplateProject(project)
      if (origin === 'demo' && !project.is_demo) return false
      if (origin === 'template' && !template) return false
      if (origin === 'mine' && (project.is_demo || template)) return false
      return matchesQuery(project, query)
    })
  }, [projects, origin, query])

  async function onCreate(event: FormEvent) {
    event.preventDefault()
    const trimmed = title.trim()
    const q = question.trim()
    if (!trimmed || !q || creating) return
    setCreating(true)
    setCreateError(null)
    try {
      const created = await startAnalysis({
        title: trimmed,
        question: q,
        text: pasted.trim() || undefined,
      })
      for (const file of files) {
        await importProjectMaterial(created.id, file)
      }
      setTitle('')
      setQuestion('')
      setPasted('')
      setFiles([])
      navigate(`/analyses/${created.id}/modeling`)
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : t('createFailed'))
    } finally {
      setCreating(false)
    }
  }

  async function onSeedDemo() {
    setSeeding(true)
    setSeedError(null)
    try {
      const demo = await seedDemo()
      navigate(`/analyses/${demo.id}/modeling`)
    } catch (err) {
      setSeedError(err instanceof Error ? err.message : t('demoSeedFailed'))
    } finally {
      setSeeding(false)
    }
  }

  async function onUseTemplate(templateId: string) {
    if (templateBusy) return
    setTemplateBusy(templateId)
    setTemplateError(null)
    try {
      const created = await templates.instantiate(templateId)
      navigate(`/analyses/${created.id}/modeling`)
    } catch (err) {
      setTemplateError(
        `${t('templateInstantiateFailed')}: ${err instanceof Error ? err.message : t('unknownError')}`,
      )
    } finally {
      setTemplateBusy(null)
    }
  }

  return (
    <div className="page">
      <div className="shell">
        <header className="topbar">
          <BrandMark subtle={t('myAnalyses')} />
          <div className="topbar-meta">
            <LanguageToggle />
            <StatusPill
              state={health.state}
              label={
                health.state === 'ready'
                  ? `API ${health.health?.status ?? 'ok'}`
                  : health.state === 'loading'
                    ? t('apiChecking')
                    : t('apiUnavailable')
              }
            />
          </div>
        </header>

        <nav className="workflow-steps" aria-label={isZh ? '工作流' : 'Workflow'}>
          <span className="workflow-step active"><b>1</b><span><strong>{isZh ? '材料收集' : 'Materials'}</strong><small>Materials</small></span></span>
          <span className="workflow-line" aria-hidden="true" />
          <span className="workflow-step"><b>2</b><span><strong>{isZh ? '建模分析' : 'Modeling'}</strong><small>Modeling</small></span></span>
          <span className="workflow-line" aria-hidden="true" />
          <span className="workflow-step"><b>3</b><span><strong>{isZh ? '基线设定' : 'Baseline'}</strong><small>Baseline</small></span></span>
          <span className="workflow-line" aria-hidden="true" />
          <span className="workflow-step"><b>4</b><span><strong>{isZh ? '结果洞察' : 'Results'}</strong><small>Results</small></span></span>
        </nav>

        <section className="concept-layout">
          <div className="analysis-board">
            <div className="board-heading">
              <div>
                <h1>{t('analysesTitle')}</h1>
                <p className="lede">{t('analysesIntro')}</p>
              </div>
              <button className="btn btn-primary" type="button" onClick={() => document.getElementById('new-analysis-form')?.scrollIntoView({ behavior: 'smooth', block: 'start' })}>
                + {t('startAnalysis')}
              </button>
            </div>
            <div className="board-tabs" role="tablist" aria-label={isZh ? '分析视图' : 'Analysis views'}>
              <span className="board-tab active">{isZh ? '我的分析' : 'My analyses'} <strong>{projects.length}</strong></span>
              <span className="board-tab">{t('templates')}</span>
              <span className="board-tab">{isZh ? '最近打开' : 'Recently opened'}</span>
            </div>
            <div className="board-toolbar">
              <label className="field search-field"><span>{t('findAnalysis')}</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t('searchPlaceholder')} /></label>
              <div className="filter-row" role="group" aria-label={t('originFilter')}>
                {(['all', 'mine', 'demo', 'template'] as const).map((value) => <button key={value} type="button" className="filter-btn" aria-pressed={origin === value} onClick={() => setOrigin(value)}>{value === 'all' ? t('all') : value === 'mine' ? t('mine') : value === 'demo' ? t('demo') : t('templateFixture')}</button>)}
              </div>
            </div>
            <div className="case-heading"><div><h2 id="template-heading">{t('templates')}</h2><p className="muted">{t('templatesIntro')}</p></div><span className="fixture-note">{t('fixtureNote')}</span></div>
            {templates.state === 'loading' ? <LoadingState label={t('templatesLoading')} rows={3} /> : null}
            {templates.state === 'error' ? <ErrorState title={t('templatesError')} body={templates.error ?? t('templatesError')} action={<button className="btn btn-secondary" type="button" onClick={() => void templates.retry()}>{t('retry')}</button>} /> : null}
            {templates.state === 'ready' ? <div className="template-grid">{templates.templates.map((template) => <TemplateRow key={template.id} template={template} busy={templateBusy === template.id} disabled={templateBusy !== null} onUse={() => void onUseTemplate(template.id)} />)}</div> : null}
            {templateError ? <p className="template-error" role="alert">{templateError}</p> : null}
          </div>

          <aside className="decision-brief" aria-label={isZh ? '决策简报' : 'Decision brief'}>
            <div className="brief-topline"><span className="brief-icon">↗</span><h2>{isZh ? '决策简报' : 'Decision brief'}</h2></div>
            <p className="brief-intro">{isZh ? '从证据到结论，聚焦当前最重要的决策。' : 'Move from evidence to a clear, reviewable decision.'}</p>
            <div className="brief-section"><div className="brief-section-title">{isZh ? '最近的分析' : 'Recent analyses'} <span>{projects.length}</span></div>{visible.slice(0, 3).map((project) => <Link key={project.id} className="brief-project" to={`/analyses/${project.id}/modeling`}><span className="brief-project-mark">{isTemplateProject(project) ? '◆' : '○'}</span><span><strong>{project.title}</strong><small>{latestCue(project, t)}</small></span><span className="brief-arrow">→</span></Link>)}{state === 'ready' && visible.length === 0 ? <p className="muted">{t('noMatches')}</p> : null}</div>
            <div className="brief-section"><div className="brief-section-title">{isZh ? '下一步行动' : 'Next action'}</div><p className="next-action">{isZh ? '选择一个完整案例，或输入自己的决策问题开始。' : 'Choose a runnable case or enter your own decision question to begin.'}</p><button className="btn btn-primary brief-action" type="button" onClick={() => document.getElementById('new-analysis-form')?.scrollIntoView({ behavior: 'smooth', block: 'start' })}>{isZh ? '添加材料' : 'Add materials'} →</button></div>
            <form id="new-analysis-form" className="composer brief-composer" onSubmit={onCreate}><h3>{t('startAnalysis')}</h3><p>{t('startAnalysisHint')}</p><label className="field"><span>{t('title')}</span><input value={title} onChange={(event) => setTitle(event.target.value)} required maxLength={200} placeholder={t('titlePlaceholder')} /></label><label className="field"><span>{t('decisionQuestion')}</span><textarea value={question} onChange={(event) => setQuestion(event.target.value)} required maxLength={8000} placeholder={t('decisionQuestionPlaceholder')} /></label><label className="field"><span>{t('pasteTextOptional')}</span><textarea value={pasted} onChange={(event) => setPasted(event.target.value)} maxLength={20000} /></label><div className={`drop-zone${dragging ? ' over' : ''}`} onDragOver={(event: DragEvent) => { event.preventDefault(); setDragging(true) }} onDragLeave={() => setDragging(false)} onDrop={(event: DragEvent) => { event.preventDefault(); setDragging(false); const next = Array.from(event.dataTransfer.files); if (next.length) setFiles(next) }}><label className="field"><span>{t('filesOptional')}</span><input type="file" multiple accept=".txt,.md,.markdown,.pdf,.csv,.xlsx,.png,.jpg,.jpeg,.json,.docx,.pptx,text/plain,text/markdown,text/csv,application/pdf,application/json,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.openxmlformats-officedocument.presentationml.presentation,image/png,image/jpeg" onChange={(event) => setFiles(event.target.files ? Array.from(event.target.files) : [])} /></label><p className="muted">{t('dropFiles')}. {t('questionOnlyOk')}{files.length ? ` · ${files.length} ${t('filesSelected')}` : ''}</p></div>{createError ? <p className="muted" role="alert">{createError}</p> : null}<button className="btn btn-primary" type="submit" disabled={creating || !title.trim() || !question.trim()}>{creating ? t('creating') : t('createAndContinue')}</button></form>
          </aside>
        </section>

        {state === 'loading' ? <LoadingState label={t('loadingAnalyses')} /> : null}

        {state === 'error' ? (
          <ErrorState
            title={t('analysesLoadError')}
            body={error ?? t('analysesLoadErrorBody')}
            action={
              <button className="btn btn-secondary" type="button" onClick={() => void reload()}>
                {t('retry')}
              </button>
            }
          />
        ) : null}

        {state === 'ready' && projects.length === 0 ? (
          <EmptyState
            title={t('noAnalyses')}
            body={t('noAnalysesBody')}
            action={
              <button
                className="btn btn-secondary"
                type="button"
                onClick={() => void onSeedDemo()}
                disabled={seeding}
              >
                {seeding ? t('loadingDemo') : t('loadDemo')}
              </button>
            }
          />
        ) : null}

        {state === 'ready' && projects.length > 0 && visible.length === 0 ? (
          <EmptyState title={t('noMatches')} body={t('noMatchesBody')} />
        ) : null}

        {state === 'ready' && visible.length > 0 ? (
          <div className="ledger">
            <div className="ledger-head">
              <span>{t('analysis')}</span>
              <span>{t('maturity')}</span>
              <span>{t('latestRecord')}</span>
              <span>{t('updated')}</span>
              <span />
            </div>
            {visible.map((project) => (
              <AnalysisRow key={project.id} project={project} />
            ))}
          </div>
        ) : null}

        {state === 'ready' && projects.length > 0 ? (
          <p className="muted" style={{ marginTop: 18 }}>
            {t('duplicateUnavailable')}{seedError ? ` ${seedError}` : ''}
          </p>
        ) : null}

        {state === 'ready' && projects.every((item) => !item.is_demo) ? (
          <p style={{ marginTop: 12 }}>
            <button className="btn btn-ghost" type="button" onClick={() => void onSeedDemo()} disabled={seeding}>
              {seeding ? t('loadingDemo') : t('loadDemo')}
            </button>
          </p>
        ) : null}
      </div>
    </div>
  )
}

function TemplateRow({
  template,
  busy,
  disabled,
  onUse,
}: {
  template: TemplateSummary
  busy: boolean
  disabled: boolean
  onUse: () => void
}) {
  const { locale, t } = useI18n()
  const name = locale === 'zh-CN' ? template.name_zh : template.name_en
  const description = locale === 'zh-CN' ? template.description_zh : template.description_en
  const category =
    template.category === 'portfolio'
      ? t('portfolio')
      : template.category === 'allocation'
        ? t('allocation')
        : t('scheduling')
  const executable = template.id === 'training-schedule' || template.id === 'product-portfolio-selection'

  return (
    <article className="template-row">
      <div className="template-copy">
        <div className="template-kicker">
          <span>{category}</span>
          <span>{template.source_count} {t('sources')}</span>
          <span className={executable ? 'template-complete' : 'template-review'}>{executable ? t('completeCase') : t('evidencePack')}</span>
        </div>
        <h3>{name}</h3>
        <p>{description}</p>
        <div className="source-badges" aria-label={`${template.source_count} ${t('sources')}`}>
          {template.source_types.map((source) => <span key={source}>{source}</span>)}
        </div>
        <div className="template-facts"><span>{t('materialsCount')} <strong>{template.source_count}</strong></span><span>{executable ? t('caseReady') : t('reviewReady')}</span></div>
      </div>
      <button className="btn btn-secondary" type="button" disabled={disabled} onClick={onUse}>
        {busy ? t('instantiating') : t('useTemplate')}
      </button>
    </article>
  )
}

function AnalysisRow({ project }: { project: ProjectSummary }) {
  const { locale, t } = useI18n()
  const href = `/analyses/${project.id}/modeling`
  const isTemplate = isTemplateProject(project)
  return (
    <div className="ledger-row">
      <Link className="ledger-title" to={href}>
        {project.is_demo ? <span className="stamp">{t('demoData')}</span> : null}
        {isTemplate ? <span className="stamp template-stamp">{t('templateFixture')}</span> : null}
        {project.title}
        {project.summary ? <small>{project.summary}</small> : null}
      </Link>
      <span className="ledger-meta">{maturityLabel(project.workflow_maturity, t)}</span>
      <span className="ledger-meta">{latestCue(project, t)}</span>
      <span className="ledger-meta">{formatTimestamp(project.updated_at, locale, t)}</span>
      <span className="row-actions">
        <Link className="btn btn-secondary" to={href}>{t('continue')}</Link>
        <button type="button" className="btn btn-ghost" disabled title={t('duplicateTitle')}>
          {t('duplicate')}
        </button>
      </span>
    </div>
  )
}
