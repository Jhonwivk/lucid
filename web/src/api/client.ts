import type {
  HealthPayload,
  Material,
  MaterialImport,
  MaterialPreview,
  ModelingBaseline,
  ModelingClaim,
  ModelingDraftRecord,
  ModelingRun,
  ClaimReviewEvent,
  ProjectCreate,
  ProjectDetail,
  ProjectSummary,
  ReadinessPayload,
  Scenario,
  ShellPayload,
  SolveRun,
  SourceSpan,
  TemplateSummary,
  Understanding,
  WorkbenchData,
} from './types'

export class ApiError extends Error {
  status: number
  hint: string | null

  constructor(message: string, status: number, hint: string | null = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.hint = hint
  }
}

const JSON_HEADERS = { 'Content-Type': 'application/json' }

function staleHint(status: number): string | null {
  if (status === 404 || status === 405) {
    return 'The process on port 8000 may be an older M0 shell without the T03 persistence routes. Restart the current API from lucid/api.'
  }
  if (status === 0) {
    return 'Nothing answered at the Vite /api proxy (127.0.0.1:8000). Start the current FastAPI process.'
  }
  return null
}

function isFormData(body: BodyInit | null | undefined): boolean {
  return typeof FormData !== 'undefined' && body instanceof FormData
}

function detailMessage(body: unknown, status: number): string {
  if (typeof body !== 'object' || body === null || !('detail' in body)) {
    return `Request failed (${status})`
  }
  const detail = (body as { detail: unknown }).detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const parts = detail.map((item) => {
      if (typeof item === 'string') return item
      if (typeof item === 'object' && item !== null && 'msg' in item) {
        return String((item as { msg: unknown }).msg)
      }
      try {
        return JSON.stringify(item)
      } catch {
        return String(item)
      }
    })
    return parts.filter(Boolean).join('; ') || `Request failed (${status})`
  }
  if (typeof detail === 'object' && detail !== null) {
    if ('message' in detail && (detail as { message: unknown }).message != null) {
      return String((detail as { message: unknown }).message)
    }
    try {
      return JSON.stringify(detail)
    } catch {
      return `Request failed (${status})`
    }
  }
  return `Request failed (${status})`
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  if (!isFormData(init?.body) && !headers.has('Content-Type')) {
    headers.set('Content-Type', JSON_HEADERS['Content-Type'])
  }

  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      ...init,
      headers,
    })
  } catch {
    throw new ApiError(
      'The LUCID API is unreachable.',
      0,
      staleHint(0),
    )
  }

  const contentType = response.headers.get('content-type') ?? ''
  if (!contentType.includes('application/json')) {
    throw new ApiError(
      `API returned a non-JSON response (${response.status}).`,
      response.status,
      staleHint(response.status) ??
        'A stale or different process may be occupying the backend port.',
    )
  }

  const body: unknown = await response.json()
  if (!response.ok) {
    throw new ApiError(detailMessage(body, response.status), response.status, staleHint(response.status))
  }

  return body as T
}

export function getHealth(): Promise<HealthPayload> {
  return request<HealthPayload>('/health')
}

export function getReadiness(): Promise<ReadinessPayload> {
  return request<ReadinessPayload>('/readiness')
}

export function getShell(): Promise<ShellPayload> {
  return request<ShellPayload>('/shell')
}

export function listProjects(): Promise<ProjectSummary[]> {
  return request<ProjectSummary[]>('/projects')
}

export function listTemplates(): Promise<TemplateSummary[]> {
  return request<TemplateSummary[]>('/templates')
}

export function instantiateTemplate(templateId: string): Promise<ProjectDetail> {
  return request<ProjectDetail>(`/templates/${templateId}/instantiate`, { method: 'POST' })
}

export function createProject(payload: ProjectCreate): Promise<ProjectDetail> {
  return request<ProjectDetail>('/projects', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function startAnalysis(payload: {
  title: string
  question: string
  text?: string
  text_label?: string
}): Promise<ProjectDetail> {
  return request<ProjectDetail>('/analyses/start', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function getProject(projectId: string): Promise<ProjectDetail> {
  return request<ProjectDetail>(`/projects/${projectId}`)
}

export function listMaterials(projectId: string): Promise<Material[]> {
  return request<Material[]>(`/projects/${projectId}/materials`)
}

export function listSourceSpans(projectId: string): Promise<SourceSpan[]> {
  return request<SourceSpan[]>(`/projects/${projectId}/source-spans`)
}

export function importProjectMaterial(projectId: string, file: File): Promise<MaterialImport> {
  const body = new FormData()
  body.append('file', file)
  return request<MaterialImport>(`/projects/${projectId}/materials/import`, {
    method: 'POST',
    body,
  })
}

export function createDirectTextMaterial(
  projectId: string,
  payload: { text: string; label?: string },
): Promise<MaterialImport> {
  return request<MaterialImport>(`/projects/${projectId}/materials/text`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function listUnderstandings(projectId: string): Promise<Understanding[]> {
  return request<Understanding[]>(`/projects/${projectId}/understandings`)
}

export function listScenarios(projectId: string): Promise<Scenario[]> {
  return request<Scenario[]>(`/projects/${projectId}/scenarios`)
}

export function listSolveRuns(projectId: string): Promise<SolveRun[]> {
  return request<SolveRun[]>(`/projects/${projectId}/solve-runs`)
}

export function seedDemoProject(): Promise<ProjectDetail> {
  return request<ProjectDetail>('/dev/seed-demo', { method: 'POST' })
}

export async function loadWorkbench(projectId: string): Promise<WorkbenchData> {
  const [project, understandings, scenarios, solveRuns, sourceSpans, modelingRuns, drafts, baselines, readiness] =
    await Promise.all([
      getProject(projectId),
      listUnderstandings(projectId),
      listScenarios(projectId),
      listSolveRuns(projectId),
      listSourceSpans(projectId),
      listModelingRuns(projectId),
      listDrafts(projectId),
      listBaselines(projectId),
      getReadiness(),
    ])
  return {
    project,
    understandings,
    scenarios,
    solveRuns,
    sourceSpans,
    modelingRuns,
    drafts,
    baselines,
    readiness,
  }
}

export function listModelingRuns(projectId: string): Promise<ModelingRun[]> {
  return request<ModelingRun[]>(`/projects/${projectId}/modeling-runs`)
}

export function getModelingRun(runId: string): Promise<ModelingRun> {
  return request<ModelingRun>(`/modeling-runs/${runId}`)
}

export function startModelingRun(projectId: string, question: string): Promise<ModelingRun> {
  return request<ModelingRun>(`/projects/${projectId}/modeling-runs`, {
    method: 'POST',
    body: JSON.stringify({ question }),
  })
}

export function resumeModelingRun(runId: string, answer: string): Promise<ModelingRun> {
  return request<ModelingRun>(`/modeling-runs/${runId}/resume`, {
    method: 'POST',
    body: JSON.stringify({ answer }),
  })
}

export function cancelModelingRun(runId: string): Promise<ModelingRun> {
  return request<ModelingRun>(`/modeling-runs/${runId}/cancel`, { method: 'POST' })
}

export function listDrafts(projectId: string): Promise<ModelingDraftRecord[]> {
  return request<ModelingDraftRecord[]>(`/projects/${projectId}/drafts`)
}

export function getDraft(draftId: string): Promise<ModelingDraftRecord> {
  return request<ModelingDraftRecord>(`/drafts/${draftId}`)
}

export function reviewClaim(
  claimId: string,
  action: string,
  editedText?: string,
): Promise<ModelingClaim> {
  return request<ModelingClaim>(`/claims/${claimId}/review`, {
    method: 'POST',
    body: JSON.stringify({ action, edited_text: editedText ?? null }),
  })
}

export function listClaimHistory(claimId: string): Promise<ClaimReviewEvent[]> {
  return request<ClaimReviewEvent[]>(`/claims/${claimId}/history`)
}

export function freezeBaseline(projectId: string, draftId: string): Promise<ModelingBaseline> {
  return request<ModelingBaseline>(`/projects/${projectId}/baseline/freeze`, {
    method: 'POST',
    body: JSON.stringify({ draft_id: draftId }),
  })
}

export function listBaselines(projectId: string): Promise<ModelingBaseline[]> {
  return request<ModelingBaseline[]>(`/projects/${projectId}/baselines`)
}

export function getMaterialPreview(
  projectId: string,
  materialId: string,
  opts?: {
    start?: number
    end?: number
    page?: number | null
    sheet?: string | null
    cell?: string | null
    runId?: string | null
    checksum?: string | null
  },
): Promise<MaterialPreview> {
  const params = new URLSearchParams()
  if (opts?.start != null) params.set('start', String(opts.start))
  if (opts?.end != null) params.set('end', String(opts.end))
  if (opts?.page != null) params.set('page', String(opts.page))
  if (opts?.sheet) params.set('sheet', opts.sheet)
  if (opts?.cell) params.set('cell_ref', opts.cell)
  if (opts?.checksum) params.set('checksum', opts.checksum)
  const query = params.toString()
  const suffix = query ? `?${query}` : ''
  if (opts?.runId) {
    return request<MaterialPreview>(`/modeling-runs/${opts.runId}/materials/${materialId}/preview${suffix}`)
  }
  return request<MaterialPreview>(`/projects/${projectId}/materials/${materialId}/preview${suffix}`)
}

export function materialContentUrl(projectId: string, materialId: string, runId?: string | null): string {
  if (runId) return `/api/modeling-runs/${runId}/materials/${materialId}/content`
  return `/api/projects/${projectId}/materials/${materialId}/content`
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.hint ? `${error.message} ${error.hint}` : error.message
  }
  if (error instanceof Error) {
    return error.message
  }
  return 'Unknown error'
}
