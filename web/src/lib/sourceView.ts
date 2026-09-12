import type { Material, MaterialPreview, ModelingRun, SourceSpan } from '../api/types'

export type SnapshotMaterial = {
  id: string
  filename?: string | null
  kind?: Material['kind'] | string | null
  media_type?: string | null
  byte_size?: number | null
  checksum?: string | null
  notes?: string | null
  created_at?: string
  snapshot_path?: string | null
  original_checksum?: string | null
  role?: string | null
  copy_error?: string | null
  spans?: SourceSpan[]
  metadata?: Record<string, unknown> | null
}

export function hasValidSnapshotIdentity(item: SnapshotMaterial | null | undefined): boolean {
  if (!item) return false
  if (item.copy_error) return false
  return Boolean(item.snapshot_path) && Boolean(item.checksum)
}

export function snapshotRunIdForSelection(
  run: ModelingRun | null | undefined,
  selectedId: string | null,
): string | null {
  if (!run?.id || !selectedId) return null
  const item = (run.snapshot?.materials ?? []).find((row) => row.id === selectedId)
  if (!item || !hasValidSnapshotIdentity(item)) return null
  return run.id
}

export function materialFromSnapshot(
  projectId: string,
  item: SnapshotMaterial,
  live: Material | null,
  fallbackCreatedAt: string,
): Material {
  const kind = (item.kind || live?.kind || 'unknown') as Material['kind']
  return {
    id: item.id,
    project_id: projectId,
    filename: item.filename || live?.filename || 'unnamed',
    kind,
    media_type: item.media_type ?? live?.media_type ?? null,
    byte_size: item.byte_size ?? live?.byte_size ?? null,
    checksum: item.checksum ?? live?.checksum ?? null,
    notes: item.notes ?? live?.notes ?? null,
    metadata: item.metadata ?? live?.metadata ?? null,
    created_at: item.created_at || live?.created_at || fallbackCreatedAt,
  }
}

export function previewMatchesRequest(
  preview: MaterialPreview | null | undefined,
  material: Material,
  runId: string | null | undefined,
): boolean {
  if (!preview || preview.material?.id !== material.id) return false
  const url = preview.content_url || ''
  if (runId) {
    if (!url.includes(`/modeling-runs/${runId}/`)) return false
    if (preview.snapshot?.material_id && preview.snapshot.material_id !== material.id) return false
    const snapChecksum = preview.snapshot?.checksum
    if (material.checksum && snapChecksum && snapChecksum !== material.checksum) return false
    return true
  }
  return !url.includes('/modeling-runs/')
}

export function compareModelingRuns(a: ModelingRun, b: ModelingRun): number {
  const updated = (b.updated_at || '').localeCompare(a.updated_at || '')
  if (updated !== 0) return updated
  const created = (b.created_at || '').localeCompare(a.created_at || '')
  if (created !== 0) return created
  return (b.id || '').localeCompare(a.id || '')
}

export function selectLatestModelingRun(
  runs: ModelingRun[],
  pinnedRunId: string | null,
): ModelingRun | null {
  if (runs.length === 0) return null
  const ordered = [...runs].sort(compareModelingRuns)
  if (pinnedRunId) {
    const pinned = ordered.find((item) => item.id === pinnedRunId)
    if (pinned) return pinned
  }
  return ordered[0] ?? null
}
