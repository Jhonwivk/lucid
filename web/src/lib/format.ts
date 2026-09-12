import type {
  ConditionKind,
  EvidenceStatus,
  LatestPointers,
  LocatorKind,
  MaterialKind,
  PremiseStatus,
  ProjectSummary,
  ReviewStatus,
  RuleKind,
  SolveRunState,
  VersionState,
  WorkflowMaturity,
} from '../api/types'
import type { Locale, Translate } from '../i18n'

export function formatTimestamp(
  value: string | null | undefined,
  locale: Locale = 'en',
  t?: Translate,
): string {
  if (!value) {
    return t ? t('unknownTime') : locale === 'zh-CN' ? '未知时间' : 'unknown time'
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return `${new Intl.DateTimeFormat(locale === 'zh-CN' ? 'zh-CN' : 'en-GB', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'UTC',
  }).format(date)} UTC`
}

export function shortId(id: string): string {
  return id.slice(0, 8)
}

export function isTemplateProject(project: { title: string }): boolean {
  return project.title.startsWith('[TEMPLATE]')
}

export function maturityLabel(value: WorkflowMaturity, t: Translate): string {
  switch (value) {
    case 'open':
      return t('open')
    case 'materials':
      return t('materials')
    case 'understanding':
      return t('modeling')
    case 'scenarios':
      return t('baseline')
    case 'results':
      return t('results')
    case 'archived':
      return t('archived')
  }
}

export function versionLabel(value: VersionState, t: Translate): string {
  switch (value) {
    case 'draft':
      return t('draft')
    case 'confirmed':
      return t('confirmed')
    case 'superseded':
      return t('superseded')
    case 'invalidated':
      return t('invalidated')
  }
}

export function reviewLabel(value: ReviewStatus, t: Translate): string {
  switch (value) {
    case 'unreviewed':
      return t('unreviewed')
    case 'accepted':
      return t('accepted')
    case 'rejected':
      return t('rejected')
    case 'needs_clarification':
      return t('needsClarification')
    case 'not_applicable':
      return t('notApplicable')
  }
}

export function evidenceLabel(value: EvidenceStatus, t: Translate): string {
  switch (value) {
    case 'present':
      return t('evidencePresent')
    case 'missing':
      return t('evidenceMissing')
    case 'unknown':
      return t('evidenceUnknown')
    case 'conflicted':
      return t('evidenceConflicted')
  }
}

export function premiseLabel(value: PremiseStatus, t: Translate): string {
  switch (value) {
    case 'known_true':
      return t('premiseTrue')
    case 'known_false':
      return t('premiseFalse')
    case 'unknown':
      return t('premiseUnknown')
    case 'missing':
      return t('premiseMissing')
  }
}

export function materialKindLabel(value: MaterialKind, t: Translate): string {
  switch (value) {
    case 'document':
      return t('kindDocument')
    case 'table':
      return t('kindTable')
    case 'image':
      return t('kindImage')
    case 'other':
      return t('kindOther')
    case 'unknown':
      return t('kindUnknown')
  }
}

export function ruleKindLabel(value: RuleKind, t: Translate): string {
  switch (value) {
    case 'hard':
      return t('ruleHard')
    case 'soft':
      return t('ruleSoft')
    case 'conditional':
      return t('ruleConditional')
    case 'objective':
      return t('ruleObjective')
    case 'assumption':
      return t('ruleAssumption')
  }
}

export function locatorKindLabel(value: LocatorKind, t: Translate): string {
  switch (value) {
    case 'text_range':
      return t('locatorTextRange')
    case 'page':
      return t('locatorPage')
    case 'cell':
      return t('locatorCell')
    case 'region':
      return t('locatorRegion')
    case 'unknown':
      return t('locatorUnknown')
  }
}

export function conditionKindLabel(value: ConditionKind, t: Translate): string {
  switch (value) {
    case 'always':
      return t('conditionAlways')
    case 'if_then':
      return t('conditionIfThen')
    case 'unknown':
      return t('conditionUnknown')
  }
}

export function solveRunStateLabel(value: SolveRunState, t: Translate): string {
  switch (value) {
    case 'pending':
      return t('runPending')
    case 'running':
      return t('runRunning')
    case 'feasible':
      return t('runFeasible')
    case 'optimal':
      return t('runOptimal')
    case 'infeasible':
      return t('runInfeasible')
    case 'unknown':
      return t('runUnknown')
    case 'model_invalid':
      return t('runModelInvalid')
    case 'failed':
      return t('runFailed')
    case 'cancelled':
      return t('runCancelled')
  }
}

export function latestCue(project: ProjectSummary, t: Translate): string {
  const latest: LatestPointers = project.latest
  if (latest.baseline_id) {
    return t('baseline')
  }
  if (latest.modeling_draft_id || latest.modeling_run_id) {
    return t('modeling')
  }
  if (latest.solve_run_id) {
    return t('solveMetadataRecorded')
  }
  if (latest.scenario_revision_no != null) {
    return `${t('scenarios')} v${latest.scenario_revision_no}`
  }
  if (latest.understanding_revision_no != null) {
    return `${t('understanding')} v${latest.understanding_revision_no}`
  }
  return t('noRecordsYet')
}

export function coverageLabel(state: string | null | undefined, t: Translate): string {
  switch (state) {
    case 'analyzed':
      return t('coverageAnalyzed')
    case 'partially_processed':
      return t('coveragePartial')
    case 'pending':
      return t('coveragePending')
    case 'unavailable':
      return t('coverageUnavailable')
    case 'unsupported':
      return t('coverageUnsupported')
    default:
      return t('unknown')
  }
}

export function claimKindHeading(kind: string, t: Translate): string {
  switch (kind) {
    case 'constraint':
      return t('claimKindConstraint')
    case 'objective':
      return t('claimKindObjective')
    case 'unknown':
      return t('claimKindUnknown')
    case 'conflict':
      return t('claimKindConflict')
    case 'parameter':
      return t('claimKindParameter')
    case 'entity':
      return t('claimKindEntity')
    case 'assumption':
      return t('claimKindAssumption')
    case 'variable':
      return t('claimKindVariable')
    case 'readiness':
      return t('claimKindReadiness')
    default:
      return kind
  }
}

export function sourceRefLabel(
  ref: {
    material_id: string
    quote?: string | null
    page?: number | null
    sheet?: string | null
    cell_ref?: string | null
    start_offset?: number | null
    end_offset?: number | null
  },
  materials: { id: string; filename: string }[],
  t: Translate,
): string {
  const material = materials.find((item) => item.id === ref.material_id)
  const name = material?.filename || t('unnamedSource')
  const bits = [name]
  if (ref.page != null) bits.push(`${t('page')} ${ref.page}`)
  if (ref.sheet) bits.push(`${t('sheet')} ${ref.sheet}`)
  if (ref.cell_ref) bits.push(`${t('cell')} ${ref.cell_ref}`)
  if (ref.quote) bits.push(`“${ref.quote.slice(0, 40)}”`)
  else if (ref.start_offset != null && ref.end_offset != null) {
    bits.push(`${ref.start_offset}–${ref.end_offset}`)
  }
  return bits.join(' · ')
}

export function matchesQuery(project: ProjectSummary, query: string): boolean {
  const needle = query.trim().toLowerCase()
  if (!needle) {
    return true
  }
  const haystack = `${project.title} ${project.summary ?? ''}`.toLowerCase()
  return haystack.includes(needle)
}
