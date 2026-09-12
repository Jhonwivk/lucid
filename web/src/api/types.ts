export type WorkspaceId = 'materials' | 'modeling' | 'baseline' | 'results'

export type WorkspaceAlias = 'understanding' | 'scenarios'

export type LoadState = 'loading' | 'ready' | 'error'

export type WorkflowMaturity =
  | 'open'
  | 'materials'
  | 'understanding'
  | 'scenarios'
  | 'results'
  | 'archived'

export type ReviewStatus =
  | 'unreviewed'
  | 'accepted'
  | 'rejected'
  | 'needs_clarification'
  | 'not_applicable'

export type EvidenceStatus = 'present' | 'missing' | 'unknown' | 'conflicted'

export type PremiseStatus = 'known_true' | 'known_false' | 'unknown' | 'missing'

export type ConditionKind = 'always' | 'if_then' | 'unknown'

export type RuleKind = 'hard' | 'soft' | 'conditional' | 'objective' | 'assumption'

export type VersionState = 'draft' | 'confirmed' | 'superseded' | 'invalidated'

export type SolveRunState =
  | 'pending'
  | 'running'
  | 'feasible'
  | 'optimal'
  | 'infeasible'
  | 'unknown'
  | 'model_invalid'
  | 'failed'
  | 'cancelled'

export type MaterialKind = 'document' | 'table' | 'image' | 'other' | 'unknown'

export type LocatorKind = 'text_range' | 'page' | 'cell' | 'region' | 'unknown'

export type OwnerKind = 'understanding' | 'scenario'

export type HealthPayload = {
  status: string
  service: string
  time: string
  database: string
}

export type WorkspaceMeta = {
  id: WorkspaceId
  label: string
  title: string
  summary: string
  status: string
}

export type ShellPayload = {
  product: string
  tagline: string
  mode: string
  workspaces: WorkspaceMeta[]
  capabilities: Record<string, string>
}

export type LatestPointers = {
  understanding_revision_id: string | null
  understanding_revision_no: number | null
  scenario_id: string | null
  scenario_revision_id: string | null
  scenario_revision_no: number | null
  formal_model_id: string | null
  solve_run_id: string | null
  modeling_run_id?: string | null
  modeling_draft_id?: string | null
  baseline_id?: string | null
}

export type UnderstandingLineageItem = {
  id: string
  revision_no: number
  parent_revision_id: string | null
  version_state: VersionState
  created_at: string
}

export type ScenarioRevisionLineageItem = {
  id: string
  revision_no: number
  parent_revision_id: string | null
  version_state: VersionState
  formal_model_id: string | null
  created_at: string
}

export type ScenarioLineageItem = {
  id: string
  name: string
  created_at: string
  revisions: ScenarioRevisionLineageItem[]
}

export type SolveRunLineageItem = {
  id: string
  run_state: SolveRunState
  claimed_execution: boolean
  execution: string
  created_at: string
}

export type ChangeEvent = {
  id: string
  project_id: string
  event_type: string
  entity_kind: string
  entity_id: string
  summary: string
  payload: Record<string, unknown> | unknown[] | null
  created_at: string
}

export type ProjectLineage = {
  understandings: UnderstandingLineageItem[]
  scenarios: ScenarioLineageItem[]
  solve_runs: SolveRunLineageItem[]
  events: ChangeEvent[]
}

export type TemplateSummary = {
  id: string
  name_en: string
  name_zh: string
  category: string
  description_en: string
  description_zh: string
  source_types: string[]
  source_count: number
}

export type ProjectSummary = {
  id: string
  title: string
  summary: string | null
  decision_question?: string | null
  workflow_maturity: WorkflowMaturity
  is_demo: boolean
  latest: LatestPointers
  created_at: string
  updated_at: string
}

export type Material = {
  id: string
  project_id: string
  filename: string
  media_type: string | null
  kind: MaterialKind
  byte_size: number | null
  checksum: string | null
  notes: string | null
  metadata?: Record<string, unknown> | null
  created_at: string
}

export type SourceSpan = {
  id: string
  project_id: string
  material_id: string
  locator_kind: LocatorKind
  page: number | null
  start_offset: number | null
  end_offset: number | null
  sheet: string | null
  cell_ref: string | null
  region: Record<string, unknown> | null
  excerpt: string | null
  created_at: string
}

export type ProjectDetail = ProjectSummary & {
  lineage: ProjectLineage
  materials: Material[]
}

export type ProjectCreate = {
  title: string
  summary?: string | null
  decision_question?: string | null
  workflow_maturity?: WorkflowMaturity
}

export type Rule = {
  id: string
  project_id: string
  owner_kind: OwnerKind
  understanding_revision_id: string | null
  scenario_revision_id: string | null
  rule_kind: RuleKind
  statement: string
  review_status: ReviewStatus
  evidence_status: EvidenceStatus
  source_span_id: string | null
  condition_kind: ConditionKind | null
  premise_status: PremiseStatus | null
  premise_text: string | null
  cost: number | null
  capacity: number | null
  permission: boolean | null
  created_at: string
}

export type Understanding = {
  id: string
  project_id: string
  revision_no: number
  parent_revision_id: string | null
  version_state: VersionState
  summary: string | null
  assumptions: string[]
  unknowns: string[]
  conflicts: string[]
  rules: Rule[]
  created_at: string
}

export type FormalModel = {
  id: string
  project_id: string
  scenario_revision_id: string | null
  name: string
  version_state: VersionState
  variable_count: number | null
  constraint_count: number | null
  objective_text: string | null
  notes: string | null
  created_at: string
}

export type ScenarioRevision = {
  id: string
  scenario_id: string
  project_id: string
  revision_no: number
  parent_revision_id: string | null
  version_state: VersionState
  based_on_understanding_id: string | null
  formal_model_id: string | null
  notes: string | null
  formal_model: FormalModel | null
  rules: Rule[]
  created_at: string
}

export type Scenario = {
  id: string
  project_id: string
  name: string
  revisions: ScenarioRevision[]
  created_at: string
}

export type ResultCandidate = {
  id: string
  project_id: string
  solve_run_id: string
  label: string | null
  objective_value: number | null
  is_selected: boolean | null
  notes: string | null
  created_at: string
}

export type SolveRun = {
  id: string
  project_id: string
  scenario_revision_id: string
  formal_model_id: string | null
  run_state: SolveRunState
  claimed_execution: boolean
  execution: string
  solver_name: string | null
  started_at: string | null
  finished_at: string | null
  message: string | null
  candidates: ResultCandidate[]
  created_at: string
}

export type WorkbenchData = {
  project: ProjectDetail
  understandings: Understanding[]
  scenarios: Scenario[]
  solveRuns: SolveRun[]
  sourceSpans: SourceSpan[]
  modelingRuns: ModelingRun[]
  drafts: ModelingDraftRecord[]
  baselines: ModelingBaseline[]
  readiness: ReadinessPayload
}

export type MaterialPreview = {
  material: Material
  spans: SourceSpan[]
  coordinate_system: string
  excerpt: string
  derived: boolean
  byte_size: number
  locator?: Record<string, unknown>
  content_url?: string
  snapshot?: {
    material_id?: string
    filename?: string | null
    checksum?: string | null
    original_checksum?: string | null
    byte_size?: number | null
    snapshot_path?: string | null
    role?: string
    frozen?: boolean
    copy_error?: string | null
  } | null
  frozen?: boolean
}

export type ReadinessPayload = {
  model: {
    name_present: boolean
    base_url_present: boolean
    api_key_present: boolean
    configured: boolean
  }
  azure_content_understanding: {
    endpoint_present: boolean
    key_present: boolean
    analyzer_id_present: boolean
    configured: boolean
    api_version: string
  }
  live_agent_possible: boolean
  live_azure_possible: boolean
  solver: string
  setup: {
    env_file: string
    model_keys: string[]
    azure_keys: string[]
  }
}

export type ModelingEvent = {
  id: string
  kind: string
  title: string
  detail: string | null
  payload: Record<string, unknown> | null
  created_at: string
}

export type ModelingClarification = {
  id: string
  question: string
  reason: string | null
  status: string
  answer_text: string | null
  answer_material_id: string | null
  created_at: string
}

export type ModelingCoverage = {
  material_id: string
  filename?: string | null
  state: string
  detail?: string | null
  needs_azure?: boolean
}

export type ModelingRun = {
  id: string
  project_id: string
  status: string
  question: string
  live_execution: boolean
  model_configured: boolean
  azure_configured: boolean
  error_code: string | null
  error_message: string | null
  coverage: ModelingCoverage[]
  events: ModelingEvent[]
  clarifications: ModelingClarification[]
  drafts: { id: string; revision_no: number; completeness: string; created_at: string }[]
  created_at: string
  updated_at: string
  heartbeat_at?: string | null
  stale_input?: boolean
  snapshot?: {
    materials?: Array<{
      id: string
      filename?: string | null
      checksum?: string | null
      snapshot_path?: string | null
      role?: string
      byte_size?: number | null
    }>
  } | null
}

export type ModelingClaim = {
  id: string
  claim_key: string
  claim_kind: string
  original_statement: string
  proposed_interpretation: string | null
  edited_statement: string | null
  grounding: string
  review_status: ReviewStatus
  modelability_status: string
  evidence_refs: EvidenceRef[]
}

export type EvidenceRef = {
  material_id: string
  source_span_id?: string | null
  precision?: string
  coordinate_system?: string
  page?: number | null
  start_offset?: number | null
  end_offset?: number | null
  sheet?: string | null
  cell_ref?: string | null
  region?: Record<string, unknown> | null
  quote?: string | null
}

export type ModelingDraftRecord = {
  id: string
  project_id: string
  run_id: string
  revision_no: number
  version_state: VersionState
  completeness: string
  draft: Record<string, unknown>
  claims: ModelingClaim[]
  created_at: string
}

export type ModelingBaseline = {
  id: string
  project_id: string
  draft_id: string
  handoff: Record<string, unknown>
  markdown: string
  created_at: string
  solver: string
  immutable?: boolean
  draft_revision_no?: number | null
  claim_count?: number
  source_count?: number
}

export type ClaimReviewEvent = {
  id: string
  previous_status: string
  new_status: string
  previous_edited_statement: string | null
  new_edited_statement: string | null
  created_at: string
}

export type MaterialImport = {
  material: Material
  spans: SourceSpan[]
}

export const WORKSPACE_IDS: WorkspaceId[] = [
  'materials',
  'modeling',
  'baseline',
  'results',
]

export const WORKSPACE_ALIASES: Record<string, WorkspaceId> = {
  understanding: 'modeling',
  scenarios: 'baseline',
}
