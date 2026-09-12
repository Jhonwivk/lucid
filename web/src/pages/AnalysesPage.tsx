import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { getProject, listScenarios } from '../api/client'
import type { ProjectDetail, ProjectSummary, Scenario, TemplateSummary, WorkspaceId } from '../api/types'
import { BrandMark } from '../components/BrandMark'
import { HomeIcon, type HomeIconName } from '../components/HomeIcon'
import { NewAnalysisDialog } from '../components/NewAnalysisDialog'
import { useHealth } from '../hooks/useHealth'
import { useProjects } from '../hooks/useProjects'
import { useTemplates } from '../hooks/useTemplates'
import { useI18n } from '../i18n'
import './AnalysesPage.css'

type View = 'analyses' | 'templates' | 'recent'
type DetailState = { data?: ProjectDetail; scenarios?: Scenario[]; error?: string }
const RECENTS = 'lucid.recent-analyses'
const PAGE_SIZE = 3
const stages: { id: WorkspaceId; zh: string; en: string }[] = [
  { id: 'materials', zh: '材料收集', en: 'Materials' },
  { id: 'modeling', zh: '建模分析', en: 'Modeling' },
  { id: 'baseline', zh: '基线设定', en: 'Baseline' },
  { id: 'results', zh: '结果洞察', en: 'Results' },
]

function readRecents(): string[] {
  try { const value: unknown = JSON.parse(localStorage.getItem(RECENTS) ?? '[]'); return Array.isArray(value) ? value.filter((id): id is string => typeof id === 'string') : [] } catch { return [] }
}
function rememberProject(id: string) {
  try { localStorage.setItem(RECENTS, JSON.stringify([id, ...readRecents().filter((value) => value !== id)].slice(0, 30))) } catch { /* Opening an analysis does not require browser storage. */ }
}
function knownTemplate(project: ProjectSummary, templates: TemplateSummary[]) {
  return templates.find((template) => project.title.includes(template.name_en) || project.title.includes(template.name_zh))
}
function projectName(project: ProjectSummary, zh: boolean) {
  const title = project.title.replace(/^\[(?:TEMPLATE|DEMO)\]\s*/i, '')
  const parts = title.split(' / ')
  return parts.length === 2 ? parts[zh ? 1 : 0] : title
}
function formatDate(value: string, zh: boolean) {
  return new Intl.DateTimeFormat(zh ? 'zh-CN' : 'en', { year: 'numeric', month: 'short', day: 'numeric' }).format(new Date(value))
}
function fileSize(size: number | null) {
  if (size === null) return ''
  return size < 1024 ? `${size} B` : size < 1024 * 1024 ? `${Math.round(size / 1024)} KB` : `${(size / 1024 / 1024).toFixed(1)} MB`
}
function fileType(filename: string) { return filename.includes('.') ? filename.split('.').at(-1)!.toUpperCase() : 'TXT' }
function executedResult(detail?: ProjectDetail) {
  return detail?.lineage.solve_runs.find((run) => run.execution !== 'not_executed' && (run.run_state === 'optimal' || run.run_state === 'feasible'))
}
function statusFor(project: ProjectSummary, detail: DetailState | undefined, zh: boolean) {
  if (executedResult(detail?.data)) return { text: zh ? '已求解' : 'Solved', tone: 'green' }
  const latestRevision = detail?.scenarios?.flatMap((scenario) => scenario.revisions).sort((a, b) => b.revision_no - a.revision_no)[0]
  const definition = latestRevision?.formal_model?.definition
  const supported = latestRevision?.formal_model?.validation?.valid === true && (definition?.family === 'training_schedule' || definition?.family === 'portfolio')
  if (supported) return { text: zh ? '可运行' : 'Runnable', tone: 'green' }
  if (project.latest.baseline_id) return { text: zh ? '已确认基线' : 'Baseline confirmed', tone: 'green' }
  if (latestRevision?.formal_model_id || project.latest.formal_model_id) return { text: zh ? '模型待确认' : 'Model needs review', tone: 'amber' }
  if (detail?.data?.lineage.understandings.some((item) => item.version_state === 'confirmed')) return { text: zh ? '模板已确认' : 'Template confirmed', tone: 'green' }
  return { text: zh ? '待完善材料' : 'In progress', tone: 'amber' }
}
function categoryIcon(category?: string): HomeIconName { return category === 'portfolio' ? 'database' : category === 'scheduling' ? 'calendar' : 'leaf' }

export function AnalysesPage() {
  const { locale, setLocale } = useI18n()
  const zh = locale === 'zh-CN'
  const navigate = useNavigate()
  const health = useHealth()
  const { projects, state, error, reload } = useProjects()
  const templates = useTemplates()
  const [view, setView] = useState<View>('analyses')
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('all')
  const [sort, setSort] = useState('updated')
  const [layout, setLayout] = useState<'grid' | 'list'>('grid')
  const [page, setPage] = useState(0)
  const [details, setDetails] = useState<Record<string, DetailState>>({})
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [composerOpen, setComposerOpen] = useState(false)
  const [busyTemplate, setBusyTemplate] = useState<string | null>(null)
  const [templateError, setTemplateError] = useState<string | null>(null)
  const [recents] = useState(readRecents)
  const copy = (cn: string, en: string) => zh ? cn : en

  const filteredProjects = useMemo(() => projects.filter((project) => {
    if (view === 'recent' && !recents.includes(project.id)) return false
    const template = knownTemplate(project, templates.templates)
    if (category !== 'all' && template?.category !== category) return false
    return `${project.title} ${project.decision_question ?? ''} ${project.summary ?? ''}`.toLowerCase().includes(query.toLowerCase())
  }).sort((a, b) => sort === 'name' ? projectName(a, zh).localeCompare(projectName(b, zh)) : view === 'recent' ? recents.indexOf(a.id) - recents.indexOf(b.id) : b.updated_at.localeCompare(a.updated_at)), [projects, view, recents, templates.templates, category, query, sort, zh])
  const filteredTemplates = templates.templates.filter((template) => (category === 'all' || template.category === category) && `${template.name_en} ${template.name_zh} ${template.description_en} ${template.description_zh}`.toLowerCase().includes(query.toLowerCase())).sort((a, b) => sort === 'name' ? (zh ? a.name_zh : a.name_en).localeCompare(zh ? b.name_zh : b.name_en) : 0)
  const count = view === 'templates' ? filteredTemplates.length : filteredProjects.length
  const maxPage = Math.max(0, Math.ceil(count / PAGE_SIZE) - 1)
  const currentPage = Math.min(page, maxPage)
  const visibleProjects = filteredProjects.slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE)
  const selected = projects.find((project) => project.id === selectedId) ?? projects[0]
  const selectedDetail = selected ? details[selected.id] : undefined
  const idsToLoad = [...new Set([...visibleProjects.map((project) => project.id), ...(selected ? [selected.id] : [])])].join(',')

  useEffect(() => {
    let active = true
    const ids = idsToLoad.split(',').filter((id) => id && !details[id])
    if (!ids.length) return
    void Promise.allSettled(ids.map(async (id) => ({ project: await getProject(id), scenarios: await listScenarios(id) }))).then((results) => {
      if (!active) return
      setDetails((current) => {
        const next = { ...current }
        results.forEach((result, index) => { next[ids[index]] = result.status === 'fulfilled' ? { data: result.value.project, scenarios: result.value.scenarios } : { error: String(result.reason instanceof Error ? result.reason.message : result.reason) } })
        return next
      })
    })
    return () => { active = false }
  }, [idsToLoad, details])

  function switchView(next: View) { setView(next); setQuery(''); setCategory('all'); setPage(0) }
  async function handleUseTemplate(id: string) {
    if (busyTemplate) return
    setBusyTemplate(id); setTemplateError(null)
    try { const project = await templates.instantiate(id); rememberProject(project.id); navigate(`/analyses/${project.id}/materials`) }
    catch (err) { setTemplateError(err instanceof Error ? err.message : copy('案例打开失败，请重试。', 'Could not open the case. Try again.')) }
    finally { setBusyTemplate(null) }
  }
  const materialCount = selectedDetail?.data?.materials.filter((material) => !material.deleted_at).length
  const confirmedCount = selectedDetail?.data?.lineage.understandings.filter((item) => item.version_state === 'confirmed').length
  const realResult = executedResult(selectedDetail?.data)
  const selectedStatus = selected ? statusFor(selected, selectedDetail, zh) : null
  const templateName = (template: TemplateSummary) => zh ? template.name_zh : template.name_en
  const loadState = view === 'templates' ? templates.state : state
  const loadError = view === 'templates' ? templates.error : error

  return <div className="lu-home">
    <header className="lu-header">
      <BrandMark to="/analyses" />
      <nav className="lu-stages" aria-label={copy('工作流程', 'Workflow')}>
        {stages.map((stage, index) => <a key={stage.id} className={`lu-stage ${index === 0 ? 'is-current' : ''}`} href={selected ? `/analyses/${selected.id}/${stage.id}` : '#analysis-board'} onClick={() => selected && rememberProject(selected.id)} aria-label={`${zh ? stage.zh : stage.en}${selected ? ` · ${projectName(selected, zh)}` : ''}`}><b>{index + 1}</b><span><strong>{zh ? stage.zh : stage.en}</strong><small>{stage.en}</small></span></a>)}
      </nav>
      <label className="lu-global-search"><HomeIcon name="search" /><input aria-label={copy('全局搜索', 'Global search')} placeholder={copy('搜索分析、模板或文件…', 'Search analyses and templates…')} value={query} onChange={(e) => { setQuery(e.target.value); setPage(0) }} /><kbd>⌘ K</kbd></label>
      <div className="lu-header-tools"><label className="lu-language"><select aria-label={copy('语言', 'Language')} value={locale} onChange={(e) => setLocale(e.target.value as 'en' | 'zh-CN')}><option value="zh-CN">中文</option><option value="en">EN</option></select><HomeIcon name="chevron" size={15}/></label><span className={`lu-api ${health.state === 'error' ? 'is-error' : ''}`}><i/>{health.state === 'ready' ? copy('API 正常', 'API online') : health.state === 'loading' ? copy('连接中', 'Connecting') : copy('API 离线', 'API offline')}</span><span className="lu-avatar" title={copy('本地个人工作区', 'Local personal workspace')}>L</span></div>
    </header>

    <main className="lu-main">
      <section className="lu-content">
        <div className="lu-heading">
          <div className="lu-title-row"><span className="lu-step-badge">1</span><h1>{copy('材料收集', 'Materials')}</h1><div className="lu-heading-actions"><button className="lu-button lu-primary" onClick={() => setComposerOpen(true)}><HomeIcon name="plus"/>{copy('新建分析', 'New analysis')}</button><button className="lu-button" onClick={() => switchView('templates')}><HomeIcon name="file"/>{copy('从模板创建', 'Use a template')}</button><button className="lu-button lu-icon-button" title={copy('刷新分析', 'Refresh analyses')} aria-label={copy('刷新分析', 'Refresh analyses')} onClick={() => { void reload(); void templates.retry(); setDetails({}) }}><HomeIcon name="refresh"/></button></div></div>
          <p>{copy('添加和整理决策所需的证据资料。查看材料、审核模型，并追溯每一个结论。', 'Organize the evidence behind your decisions. Review models and trace every conclusion.')}</p>
        </div>

        <section className="lu-board" id="analysis-board" aria-label={copy('分析工作区', 'Analysis workspace')}>
          <div className="lu-board-toolbar">
            <div className="lu-tabs" role="group" aria-label={copy('分析视图', 'Analysis views')}>{(['analyses', 'templates', 'recent'] as View[]).map((item) => <button key={item} aria-pressed={view === item} className={view === item ? 'is-active' : ''} onClick={() => switchView(item)}>{item === 'analyses' ? `${copy('我的分析', 'My analyses')} (${projects.length})` : item === 'templates' ? copy('模板库', 'Templates') : copy('最近打开', 'Recently opened')}</button>)}</div>
            <div className="lu-filters"><label className="lu-search"><HomeIcon name="search" size={19}/><input value={query} onChange={(e) => { setQuery(e.target.value); setPage(0) }} aria-label={copy('搜索分析', 'Search analyses')} placeholder={copy('搜索分析…', 'Search…')}/></label><label className="lu-select"><select value={category} aria-label={copy('类型筛选', 'Type filter')} onChange={(e) => { setCategory(e.target.value); setPage(0) }}><option value="all">{copy('全部类型', 'All types')}</option><option value="scheduling">{copy('排程', 'Scheduling')}</option><option value="portfolio">{copy('组合选择', 'Portfolio')}</option><option value="allocation">{copy('分配', 'Allocation')}</option></select><HomeIcon name="chevron" size={15}/></label><label className="lu-select"><select value={sort} aria-label={copy('排序', 'Sort')} onChange={(e) => setSort(e.target.value)}><option value="updated">{copy('最近更新', 'Last updated')}</option><option value="name">{copy('按名称', 'By name')}</option></select><HomeIcon name="chevron" size={15}/></label><div className="lu-view-toggle" role="group" aria-label={copy('展示方式', 'Display mode')}><button aria-label={copy('网格视图', 'Grid view')} aria-pressed={layout === 'grid'} onClick={() => setLayout('grid')}><HomeIcon name="grid" size={18}/></button><button aria-label={copy('列表视图', 'List view')} aria-pressed={layout === 'list'} onClick={() => setLayout('list')}><HomeIcon name="list" size={18}/></button></div></div>
          </div>

          {loadState === 'loading' ? <div className="lu-state" role="status">{copy('正在加载工作区…', 'Loading workspace…')}</div> : loadState === 'error' ? <div className="lu-state" role="alert"><h3>{copy('暂时无法加载', 'Unable to load')}</h3><p>{loadError}</p><button className="lu-button" onClick={() => view === 'templates' ? void templates.retry() : void reload()}>{copy('重试', 'Retry')}</button></div> : count === 0 ? <div className="lu-state"><HomeIcon name="file" size={36}/><h3>{query || category !== 'all' ? copy('没有匹配的分析', 'No matches') : view === 'recent' ? copy('还没有最近打开的分析', 'No recently opened analyses') : copy('从一个决策问题开始', 'Start with a decision')}</h3><p>{copy('你可以新建分析，也可以从模板库中打开完整案例。', 'Create an analysis or open a case from the template library.')}</p><button className="lu-button lu-primary" onClick={() => setComposerOpen(true)}>{copy('新建分析', 'New analysis')}</button></div> : <div className={`lu-card-grid ${layout === 'list' ? 'is-list' : ''}`}>
            {view === 'templates' ? filteredTemplates.slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE).map((template, index) => <article className="lu-card" key={template.id}>
              <div className="lu-card-top"><span className={`lu-card-icon tone-${index % 3}`}><HomeIcon name={categoryIcon(template.category)} size={29}/></span><span className={`lu-status ${['training-schedule', 'product-portfolio-selection'].includes(template.id) ? 'green' : 'amber'}`}><i/>{['training-schedule', 'product-portfolio-selection'].includes(template.id) ? copy('完整案例', 'Runnable case') : copy('材料案例', 'Evidence case')}</span></div>
              <h2>{templateName(template)}</h2><p className="lu-card-description">{zh ? template.description_zh : template.description_en}</p><div className="lu-tags"><span>{template.category === 'portfolio' ? copy('组合选择', 'Portfolio') : template.category === 'allocation' ? copy('资源分配', 'Allocation') : copy('排程', 'Scheduling')}</span><span>{copy('虚构案例', 'Fictional case')}</span></div>
              <div className="lu-evidence"><span className="lu-evidence-icon"><HomeIcon name="file"/></span><span><strong>{copy('证据资料', 'Evidence')}</strong><small>{template.source_count} {copy('份来源', 'sources')}</small></span></div><ul className="lu-source-list">{template.source_types.map((type) => <li key={type}><span className={`lu-file-icon ${type.toLowerCase()}`}><HomeIcon name="file" size={24}/></span><span><strong>{type} {copy('来源材料', 'source material')}</strong><small>{copy('随案例一起导入', 'Included with the case')}</small></span></li>)}</ul>
              <div className="lu-card-bottom"><small>{copy('模板案例', 'Template case')}</small><button className="lu-open" disabled={busyTemplate !== null} onClick={() => void handleUseTemplate(template.id)}><HomeIcon name="play" size={14}/>{busyTemplate === template.id ? copy('打开中…', 'Opening…') : copy('打开案例', 'Open case')}</button></div>
            </article>) : visibleProjects.map((project, index) => {
              const detail = details[project.id]
              const template = knownTemplate(project, templates.templates)
              const status = statusFor(project, detail, zh)
              const materials = detail?.data?.materials.filter((material) => !material.deleted_at)
              const materialPath = `/analyses/${project.id}/materials`
              const description = template ? (zh ? template.description_zh : template.description_en) : project.decision_question ?? project.summary
              return <article className="lu-card" key={project.id}>
                <div className="lu-card-top"><span className={`lu-card-icon tone-${index % 3}`}><HomeIcon name={categoryIcon(template?.category)} size={29}/></span><span className={`lu-status ${status.tone}`}><i/>{status.text}</span><details className="lu-card-menu"><summary aria-label={`${projectName(project, zh)} · ${copy('更多操作', 'More actions')}`}><HomeIcon name="more" size={19}/></summary><div><button onClick={(e) => { setSelectedId(project.id); e.currentTarget.closest('details')?.removeAttribute('open') }}>{copy('查看决策简报', 'Show decision brief')}</button><Link to={materialPath} onClick={() => rememberProject(project.id)}>{copy('查看全部材料', 'View all materials')}</Link></div></details></div>
                <h2 title={project.title}><Link to={materialPath} onClick={() => rememberProject(project.id)}>{projectName(project, zh)}</Link></h2><p className="lu-card-description">{description ?? copy('补充决策问题与材料，开始整理你的分析。', 'Add a question and materials to begin your analysis.')}</p><div className="lu-tags"><span>{template?.category === 'portfolio' ? copy('组合选择', 'Portfolio') : template?.category === 'scheduling' ? copy('培训排程', 'Scheduling') : copy('业务建模', 'Modeling')}</span><span>{project.is_demo ? copy('演示数据', 'Demo') : template ? copy('模板案例', 'Template') : copy('个人分析', 'Personal')}</span></div>
                <Link className="lu-evidence" to={materialPath} onClick={() => rememberProject(project.id)}><span className="lu-evidence-icon"><HomeIcon name="file"/></span><span><strong>{copy('证据资料', 'Evidence')}</strong><small>{materials ? `${materials.length} ${copy('份来源', 'sources')}` : detail?.error ? copy('加载失败', 'Unavailable') : copy('加载中…', 'Loading…')}</small></span><HomeIcon name="chevron" size={17}/></Link>
                {detail?.error ? <p className="lu-source-error" role="alert">{copy('材料加载失败，请刷新重试。', 'Could not load sources. Refresh to retry.')}</p> : <ul className="lu-source-list">{materials?.slice(0, 3).map((material) => <li key={material.id}><Link to={materialPath} onClick={() => rememberProject(project.id)}><span className={`lu-file-icon ${fileType(material.filename).toLowerCase()}`}><HomeIcon name="file" size={25}/></span><span><strong title={material.filename}>{material.filename}</strong><small>{fileType(material.filename)}{material.byte_size !== null ? ` · ${fileSize(material.byte_size)}` : ''}</small></span></Link></li>)}{materials?.length === 0 ? <li className="lu-source-empty">{copy('尚未添加材料', 'No materials yet')}</li> : null}</ul>}
                <div className="lu-card-bottom"><small>{copy('更新于 ', 'Updated ')}{formatDate(project.updated_at, zh)}</small><Link className="lu-open" to={`/analyses/${project.id}/modeling`} onClick={() => rememberProject(project.id)}><HomeIcon name="play" size={14}/>{copy('打开分析', 'Open')}</Link></div>
              </article>
            })}
          </div>}
          {templateError ? <p role="alert" className="lu-source-error">{templateError}</p> : null}
          {count > PAGE_SIZE ? <div className="lu-pagination"><span>{currentPage * PAGE_SIZE + 1}–{Math.min((currentPage + 1) * PAGE_SIZE, count)} / {count}</span><button disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>{copy('上一页', 'Previous')}</button><button disabled={currentPage === maxPage} onClick={() => setPage(currentPage + 1)}>{copy('下一页', 'Next')}</button></div> : null}
        </section>
      </section>

      <aside className="lu-brief" aria-labelledby="brief-title"><div className="lu-brief-title"><h2 id="brief-title">{copy('决策简报', 'Decision brief')}</h2><button className="lu-bare-icon" aria-label={copy('刷新简报', 'Refresh brief')} onClick={() => setDetails({})}><HomeIcon name="refresh" size={18}/></button></div><p className="lu-brief-intro">{copy('从证据到结论，聚焦当前最重要的决策。', 'From evidence to conclusions. Focus on your next decision.')}</p>
        <div className="lu-brief-body">
          <section className="lu-recent"><div className="lu-section-title"><HomeIcon name="clock" size={22}/><h3>{copy('最近的分析', 'Recent analysis')}</h3><button className="lu-text-button" onClick={() => switchView('analyses')}>{copy('查看全部', 'View all')}<HomeIcon name="arrow" size={16}/></button></div>{selected ? <Link className="lu-recent-project" to={`/analyses/${selected.id}/materials`} onClick={() => rememberProject(selected.id)}><span className="lu-card-icon"><HomeIcon name="database" size={27}/></span><span><strong>{projectName(selected, zh)}</strong><small>{copy('更新于 ', 'Updated ')}{formatDate(selected.updated_at, zh)}</small></span><span className={`lu-status ${selectedStatus?.tone}`}>{selectedStatus?.text}</span></Link> : <p className="lu-empty-brief">{state === 'error' ? copy('分析加载失败', 'Analyses unavailable') : state === 'loading' ? copy('加载中…', 'Loading…') : copy('新建分析后，这里会显示最近的决策。', 'Your latest decision will appear here.')}</p>}</section>
          <section className="lu-findings"><div className="lu-section-title"><HomeIcon name="insight" size={22}/><h3>{copy('关键发现', 'Key findings')}</h3><span>{copy('（基于当前记录）', '(current records)')}</span></div>{selectedDetail?.data ? <>
            <Link className="lu-finding" to={`/analyses/${selected!.id}/materials`}><span className={`lu-finding-mark ${materialCount ? 'green' : 'neutral'}`}><HomeIcon name={materialCount ? 'check' : 'pin'} size={15}/></span><span><strong>{materialCount ? copy('来源材料已归档，可追溯原文', 'Source materials are available for review') : copy('尚未添加来源材料', 'No source materials yet')}</strong><small>{copy('来自 ', '')}{materialCount} {copy('份有效材料', 'available sources')}</small></span><HomeIcon name="chevron" size={17}/></Link>
            <Link className="lu-finding" to={`/analyses/${selected!.id}/baseline`}><span className={`lu-finding-mark ${confirmedCount || selected!.latest.baseline_id ? 'green' : 'neutral'}`}><HomeIcon name={confirmedCount || selected!.latest.baseline_id ? 'check' : 'pin'} size={15}/></span><span><strong>{confirmedCount || selected!.latest.baseline_id ? copy('已保存确认版本，可查看基线', 'A confirmed version is available') : copy('建模内容尚待审核确认', 'Modeling content awaits review')}</strong><small>{selected!.latest.baseline_id ? copy('Agent 建模基线', 'Agent modeling baseline') : confirmedCount ? copy('模板确认版本', 'Confirmed template version') : copy('审核后继续建立基线', 'Review the evidence to continue')}</small></span><HomeIcon name="chevron" size={17}/></Link>
            <Link className="lu-finding" to={`/analyses/${selected!.id}/results`}><span className={`lu-finding-mark ${realResult ? 'green' : 'neutral'}`}><HomeIcon name={realResult ? 'check' : 'pin'} size={15}/></span><span><strong>{realResult ? copy('已生成确定性求解结果', 'Deterministic results are available') : copy('尚无已执行的求解结果', 'No executed solver results yet')}</strong><small>{realResult ? realResult.run_state : copy('进入结果工作区检查模型并运行', 'Check the model and run the solver')}</small></span><HomeIcon name="chevron" size={17}/></Link>
          </> : <p className="lu-empty-brief">{selectedDetail?.error ? copy('无法读取记录，请刷新简报重试。', 'Could not read records. Refresh the brief.') : selected ? copy('正在读取材料与版本记录…', 'Reading materials and revisions…') : copy('添加材料后，在此查看真实记录。', 'Add materials to see the evidence here.')}</p>}</section>
          <section className="lu-next"><div className="lu-section-title"><HomeIcon name="bolt" size={24}/><h3>{copy('下一步行动', 'Next action')}</h3></div><p>{selected ? copy('补充当前分析的资料，继续完善建模输入。', 'Add evidence to complete the current analysis.') : copy('输入一个决策问题，开始你的第一个分析。', 'Start your first analysis with a decision question.')}</p>{selected ? <Link className="lu-button lu-primary" to={`/analyses/${selected.id}/materials`} onClick={() => rememberProject(selected.id)}><HomeIcon name="file" size={18}/>{copy('添加资料', 'Add materials')}</Link> : <button className="lu-button lu-primary" onClick={() => setComposerOpen(true)}><HomeIcon name="plus"/>{copy('新建分析', 'New analysis')}</button>}</section>
        </div>
        <section className="lu-resources"><div className="lu-section-title"><HomeIcon name="book" size={22}/><h3>{copy('常用资源', 'Resources')}</h3><button className="lu-text-button" onClick={() => switchView('templates')}>{copy('查看全部', 'View all')}<HomeIcon name="arrow" size={16}/></button></div><div className="lu-resource-grid">{templates.templates.slice(0, 3).map((template, index) => <button key={template.id} disabled={busyTemplate !== null} onClick={() => void handleUseTemplate(template.id)} title={templateName(template)}><span className={`lu-file-icon ${index === 1 ? 'docx' : 'xlsx'}`}><HomeIcon name="file" size={25}/></span><span><strong>{templateName(template)}</strong><small>{template.source_types.slice(0, 2).join(' / ')}</small></span></button>)}</div>{templates.state === 'error' ? <button className="lu-text-button" onClick={() => void templates.retry()}>{copy('重新加载模板', 'Retry templates')}</button> : null}{templateError && view !== 'templates' ? <p role="alert" className="lu-source-error">{templateError}</p> : null}</section>
      </aside>
    </main>
    <NewAnalysisDialog open={composerOpen} onClose={() => setComposerOpen(false)}/>
  </div>
}
