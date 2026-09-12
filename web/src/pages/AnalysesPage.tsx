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

        <section className="masthead">
          <div>
            <h1>{t('analysesTitle')}</h1>
            <p className="lede">{t('analysesIntro')}</p>
            <div className="home-brief">
              <div className="brief-heading"><span className="brief-dot" /> {isZh ? '当前工作区' : 'Current workspace'}</div>
              <p>{isZh ? '从一份决策问题开始，逐步整理材料、确认基线，再运行确定性求解。' : 'Start with a decision question, organize evidence, confirm a baseline, then run a deterministic solve.'}</p>
              <div className="brief-links">
                <span>{isZh ? '材料' : 'Analyses'} <strong>{projects.length}</strong></span>
                <span>{isZh ? '可运行案例' : 'Runnable cases'} <strong>{templates.templates.filter((item) => item.id === 'training-schedule' || item.id === 'product-portfolio-selection').length}</strong></span>
              </div>
            </div>
          </div>
          <form className="composer" onSubmit={onCreate}>
            <h2>{t('startAnalysis')}</h2>
            <p>{t('startAnalysisHint')}</p>
            <label className="field">
              <span>{t('title')}</span>
              <input
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                required
                maxLength={200}
                placeholder={t('titlePlaceholder')}
              />
            </label>
            <label className="field">
              <span>{t('decisionQuestion')}</span>
              <textarea
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                required
                maxLength={8000}
                placeholder={t('decisionQuestionPlaceholder')}
              />
            </label>
            <label className="field">
              <span>{t('pasteTextOptional')}</span>
              <textarea
                value={pasted}
                onChange={(event) => setPasted(event.target.value)}
                maxLength={20000}
              />
            </label>
            <div
              className={`drop-zone${dragging ? ' over' : ''}`}
              onDragOver={(event: DragEvent) => {
                event.preventDefault()
                setDragging(true)
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(event: DragEvent) => {
                event.preventDefault()
                setDragging(false)
                const next = Array.from(event.dataTransfer.files)
                if (next.length) setFiles(next)
              }}
            >
              <label className="field">
                <span>{t('filesOptional')}</span>
                <input
                  type="file"
                  multiple
                  accept=".txt,.md,.markdown,.pdf,.csv,.xlsx,.png,.jpg,.jpeg,.json,.docx,.pptx,text/plain,text/markdown,text/csv,application/pdf,application/json,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.openxmlformats-officedocument.presentationml.presentation,image/png,image/jpeg"
                  onChange={(event) => setFiles(event.target.files ? Array.from(event.target.files) : [])}
                />
              </label>
              <p className="muted">
                {t('dropFiles')}. {t('questionOnlyOk')}
                {files.length ? ` · ${files.length} ${t('filesSelected')}` : ''}
              </p>
            </div>
            {createError ? <p className="muted" role="alert">{createError}</p> : null}
            <button className="btn btn-primary" type="submit" disabled={creating || !title.trim() || !question.trim()}>
              {creating ? t('creating') : t('createAndContinue')}
            </button>
          </form>
        </section>

        <section className="template-section" aria-labelledby="template-heading">
          <div className="section-heading">
            <div>
              <h2 id="template-heading">{t('templates')}</h2>
              <p className="muted">{t('templatesIntro')}</p>
            </div>
            <span className="fixture-note">{t('fixtureNote')}</span>
          </div>

          {templates.state === 'loading' ? (
            <LoadingState label={t('templatesLoading')} rows={3} />
          ) : null}
          {templates.state === 'error' ? (
            <ErrorState
              title={t('templatesError')}
              body={templates.error ?? t('templatesError')}
              action={
                <button className="btn btn-secondary" type="button" onClick={() => void templates.retry()}>
                  {t('retry')}
                </button>
              }
            />
          ) : null}
          {templates.state === 'ready' ? (
            <div className="template-grid">
              {templates.templates.map((template) => (
                <TemplateRow
                  key={template.id}
                  template={template}
                  busy={templateBusy === template.id}
                  disabled={templateBusy !== null}
                  onUse={() => void onUseTemplate(template.id)}
                />
              ))}
            </div>
          ) : null}
          {templateError ? <p className="template-error" role="alert">{templateError}</p> : null}
        </section>

        <div className="toolbar">
          <label className="field search-field">
            <span>{t('findAnalysis')}</span>
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={t('searchPlaceholder')}
            />
          </label>
          <div className="filter-row" role="group" aria-label={t('originFilter')}>
            {(['all', 'mine', 'demo', 'template'] as const).map((value) => (
              <button
                key={value}
                type="button"
                className="filter-btn"
                aria-pressed={origin === value}
                onClick={() => setOrigin(value)}
              >
                {value === 'all'
                  ? t('all')
                  : value === 'mine'
                    ? t('mine')
                    : value === 'demo'
                      ? t('demo')
                      : t('templateFixture')}
              </button>
            ))}
          </div>
        </div>

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
