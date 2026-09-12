import { useState, type ChangeEvent } from 'react'
import { Link } from 'react-router-dom'
import { EmptyState } from '../../components/EmptyState'
import { NullValue, Quantity } from '../../components/NullValue'
import { SourceViewer } from '../../components/SourceViewer'
import { createDirectTextMaterial, importProjectMaterial } from '../../api/client'
import type { Material, SourceSpan } from '../../api/types'
import { useI18n, type Translate } from '../../i18n'
import { formatTimestamp, locatorKindLabel, materialKindLabel } from '../../lib/format'

const ACCEPT = [
  '.txt',
  '.md',
  '.markdown',
  '.pdf',
  '.csv',
  '.xlsx',
  '.png',
  '.jpg',
  '.jpeg',
  '.json',
  '.docx',
  '.pptx',
  'text/plain',
  'text/markdown',
  'text/csv',
  'application/json',
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  'image/png',
  'image/jpeg',
].join(',')

const SPAN_PREVIEW = 40

type IntakeRow = {
  name: string
  ok: boolean
  detail: string
}

type MaterialsWorkspaceProps = {
  projectId: string
  materials: Material[]
  sourceSpans: SourceSpan[]
  reload: () => Promise<void> | void
}

function spanLooksEmpty(span: SourceSpan): boolean {
  const excerpt = span.excerpt ?? ''
  if (excerpt.includes('No extractable text') || excerpt.includes('(empty file')) return true
  if (excerpt.includes('blank/unknown')) return true
  return false
}

function metadataString(material: Material, key: string): string | null {
  const value = material.metadata?.[key]
  return typeof value === 'string' ? value : null
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>
  }
  return null
}

function asList(value: unknown): unknown[] {
  return Array.isArray(value) ? value : []
}

function regionStateLabel(state: string, t: Translate): string {
  switch (state) {
    case 'box':
      return t('regionBox')
    case 'full_image':
      return t('regionFullImage')
    case 'unknown':
      return t('regionUnknown')
    default:
      return state
  }
}

function unitHintText(material: Material): string {
  const units = asList(material.metadata?.units)
  const parts: string[] = []
  for (const item of units) {
    const rec = asRecord(item)
    if (!rec) continue
    const header = typeof rec.header === 'string' ? rec.header : ''
    const unit = typeof rec.unit === 'string' ? rec.unit : ''
    if (header && unit) parts.push(`${header} → ${unit}`)
  }
  return parts.join('; ')
}

function sheetNames(material: Material): string[] {
  const names = asList(material.metadata?.sheet_names)
  return names.filter((item): item is string => typeof item === 'string')
}

function isDirectText(material: Material): boolean {
  return metadataString(material, 'source_origin') === 'direct_text'
}

function TableSummary({ material, t }: { material: Material; t: Translate }) {
  const sheets = sheetNames(material)
  const hidden = asList(material.metadata?.hidden_sheet_names).filter(
    (item): item is string => typeof item === 'string',
  )
  const units = unitHintText(material)
  const rowCount = material.metadata?.row_count
  const columnCount = material.metadata?.column_count
  const firstSheet = asRecord(asList(material.metadata?.sheets)[0])
  return (
    <div className="intake-summary">
      <p>
        {t('tableStructure')}: {sheets.length} {t('sheetCount')}
        {sheets.length ? ` (${sheets.join(', ')})` : ''}.
        {typeof rowCount === 'number' ? ` ${t('rowCount')} ${rowCount}.` : null}
        {typeof columnCount === 'number' ? ` ${t('columnCount')} ${columnCount}.` : null}
        {firstSheet && typeof firstSheet.row_count === 'number' && typeof rowCount !== 'number'
          ? ` ${t('rowCount')} ${String(firstSheet.row_count)}.`
          : null}
      </p>
      <p>{t('formulaNotRecalculated')}</p>
      <p>{t('blankUnknown')}</p>
      {hidden.length > 0 ? <p>{t('hiddenSheet')}: {hidden.join(', ')}</p> : null}
      <p>{t('unitHints')}: {units || t('unitUnknown')}</p>
    </div>
  )
}

function ImageSummary({ material, t }: { material: Material; t: Translate }) {
  const width = material.metadata?.pixel_width
  const height = material.metadata?.pixel_height
  const format = metadataString(material, 'image_format')
  const mode = metadataString(material, 'image_mode')
  const semantic = metadataString(material, 'semantic_understanding') ?? 'not_performed'
  return (
    <div className="intake-summary">
      <p>
        {t('imageMetadata')}:{' '}
        {typeof width === 'number' && typeof height === 'number'
          ? `${width}×${height}`
          : t('unspecified')}
        {format ? ` · ${format}` : ''}
        {mode ? ` · ${mode}` : ''}
      </p>
      <p>{t('fullImageProvenance')}</p>
      <p>
        {t('semanticUnderstanding')}: {semantic === 'not_performed' ? t('semanticNotPerformed') : semantic}
      </p>
    </div>
  )
}

function RegionMeta({ span, t }: { span: SourceSpan; t: Translate }) {
  const region = span.region
  if (!region) return <span>{t('regionUnknown')}</span>
  const state = typeof region.region_state === 'string' ? region.region_state : 'unknown'
  const x = typeof region.x === 'number' ? region.x : null
  const y = typeof region.y === 'number' ? region.y : null
  const width = typeof region.width === 'number' ? region.width : null
  const height = typeof region.height === 'number' ? region.height : null
  return (
    <>
      <span>{t('regionState')} {regionStateLabel(state, t)}</span>
      {x != null && y != null && width != null && height != null ? (
        <span>
          {t('regionBox')} {x.toFixed(2)},{y.toFixed(2)} {width.toFixed(2)}×{height.toFixed(2)}
        </span>
      ) : (
        <span>{regionStateLabel(state === 'box' ? 'unknown' : state, t)}</span>
      )}
    </>
  )
}

export function MaterialsWorkspace({
  projectId,
  materials,
  sourceSpans,
  reload,
}: MaterialsWorkspaceProps) {
  const { locale, t } = useI18n()
  const [files, setFiles] = useState<File[]>([])
  const [busy, setBusy] = useState(false)
  const [progress, setProgress] = useState<string | null>(null)
  const [results, setResults] = useState<IntakeRow[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(materials[0]?.id ?? null)
  const [directText, setDirectText] = useState('')
  const [directLabel, setDirectLabel] = useState('')
  const [textBusy, setTextBusy] = useState(false)
  const [textResult, setTextResult] = useState<IntakeRow | null>(null)

  function onPick(event: ChangeEvent<HTMLInputElement>) {
    const next = event.target.files ? Array.from(event.target.files) : []
    setFiles(next)
    setResults([])
  }

  async function onAddText() {
    if (!directText.trim() || textBusy || busy) return
    setTextBusy(true)
    setTextResult(null)
    try {
      const imported = await createDirectTextMaterial(projectId, {
        text: directText,
        label: directLabel.trim() || undefined,
      })
      setTextResult({
        name: imported.material.filename,
        ok: true,
        detail: `${t('intakeOk')} (${imported.spans.length} ${imported.spans.length === 1 ? t('sourceSpan') : t('sourceSpans')})`,
      })
      setDirectText('')
      setDirectLabel('')
      await reload()
    } catch (err) {
      setTextResult({
        name: directLabel.trim() || t('enterTextTitle'),
        ok: false,
        detail: `${t('intakeFailed')}: ${err instanceof Error ? err.message : t('unknownError')}`,
      })
    } finally {
      setTextBusy(false)
    }
  }

  async function onImport() {
    if (!files.length || busy || textBusy) return
    setBusy(true)
    setResults([])
    const rows: IntakeRow[] = []
    let anyOk = false
    try {
      for (let index = 0; index < files.length; index += 1) {
        const file = files[index]
        setProgress(`${t('intakeProgress')} ${index + 1} ${t('ofFiles')} ${files.length}: ${file.name}`)
        try {
          const imported = await importProjectMaterial(projectId, file)
          anyOk = true
          rows.push({
            name: file.name,
            ok: true,
            detail: `${t('intakeOk')} (${imported.spans.length} ${imported.spans.length === 1 ? t('sourceSpan') : t('sourceSpans')})`,
          })
        } catch (err) {
          rows.push({
            name: file.name,
            ok: false,
            detail: `${t('intakeFailed')}: ${err instanceof Error ? err.message : t('unknownError')}`,
          })
        }
        setResults([...rows])
      }
      if (anyOk) {
        await reload()
      }
    } finally {
      setBusy(false)
      setProgress(null)
    }
  }

  const intakeBusy = busy || textBusy

  return (
    <div className="stage">
      <div className="notice honest">{t('materialNotice')}</div>

      <div className="intake-peers">
        <section className="composer intake-composer" aria-busy={intakeBusy}>
          <h2>{t('enterTextTitle')}</h2>
          <p>{t('enterTextHint')}</p>
          <label className="field">
            <span>{t('enterTextBody')}</span>
            <textarea
              value={directText}
              disabled={intakeBusy}
              rows={8}
              placeholder={t('enterTextPlaceholder')}
              onChange={(event) => {
                setDirectText(event.target.value)
                setTextResult(null)
              }}
            />
          </label>
          <label className="field">
            <span>{t('enterTextLabel')}</span>
            <input
              type="text"
              value={directLabel}
              disabled={intakeBusy}
              placeholder={t('enterTextLabelPlaceholder')}
              onChange={(event) => setDirectLabel(event.target.value)}
            />
          </label>
          <label className="field">
            <span>{t('uploadFilesTitle')}</span>
            <input
              type="file"
              accept={ACCEPT}
              multiple
              disabled={intakeBusy}
              onChange={onPick}
            />
          </label>
          {files.length === 0 ? (
            <p className="muted">{t('dropFiles')}</p>
          ) : (
            <ul className="intake-files">
              {files.map((file) => (
                <li key={`${file.name}-${file.size}-${file.lastModified}`}>
                  <span>{file.name}</span>
                  <span className="muted">{file.size} {t('bytes')}</span>
                </li>
              ))}
            </ul>
          )}
          <div className="intake-actions">
            <button
              className="btn btn-primary"
              type="button"
              disabled={intakeBusy || !directText.trim()}
              onClick={() => void onAddText()}
            >
              {textBusy ? t('addingText') : t('addText')}
            </button>
            <button
              className="btn btn-secondary"
              type="button"
              disabled={intakeBusy || files.length === 0}
              onClick={() => void onImport()}
            >
              {busy ? t('intakeImporting') : t('intakeImport')}
            </button>
          </div>
          {progress ? <p className="muted">{progress}</p> : null}
          {textResult ? (
            <ul className="intake-results">
              <li className={textResult.ok ? 'ok' : 'fail'}>
                <strong>{textResult.name}</strong>
                <span>{textResult.detail}</span>
              </li>
            </ul>
          ) : null}
          {results.length > 0 ? (
            <ul className="intake-results">
              {results.map((row) => (
                <li key={row.name + row.detail} className={row.ok ? 'ok' : 'fail'}>
                  <strong>{row.name}</strong>
                  <span>{row.detail}</span>
                </li>
              ))}
            </ul>
          ) : null}
        </section>
      </div>

      {materials.length === 0 ? (
        <EmptyState title={t('noMaterials')} body={t('noMaterialsBody')} />
      ) : (
        <div className="stack">
          <p className="muted">
            {materials.length} {materials.length === 1 ? t('material') : t('materialsPlural')}, {' '}
            {sourceSpans.length} {sourceSpans.length === 1 ? t('sourceSpan') : t('sourceSpans')} ({t('storedBytes')}).
          </p>
          <SourceViewer
            projectId={projectId}
            material={materials.find((item) => item.id === selectedId) ?? materials[0]}
            spans={sourceSpans.filter((span) => span.material_id === (selectedId ?? materials[0]?.id))}
          />
          {materials.map((material) => {
            const spans = sourceSpans.filter((span) => span.material_id === material.id)
            const preview = spans.slice(0, SPAN_PREVIEW)
            const decodeStatus = metadataString(material, 'decode_status')
            const displayName = metadataString(material, 'display_label') || material.filename
            return (
              <article
                className={`fact present${material.id === selectedId ? ' selected-source' : ''}`}
                key={material.id}
              >
                <div className="fact-label">{materialKindLabel(material.kind, t)}</div>
                <h3>{displayName}</h3>
                <button className="btn btn-ghost" type="button" onClick={() => setSelectedId(material.id)}>
                  {t('inspectPreview')}
                </button>
                <div className="meta-row">
                  <span>{t('type')} {material.media_type ?? t('unspecified')}</span>
                  {isDirectText(material) ? <span>{t('sourceOriginDirectText')}</span> : null}
                  <Quantity name={t('bytes')} value={material.byte_size} />
                  <span>{spans.length} {t('sourceSpans')}</span>
                  <span>{t('recorded')} {formatTimestamp(material.created_at, locale, t)}</span>
                </div>
                <details className="tech-details">
                  <summary>{t('technicalDetails')}</summary>
                  <p>{t('checksum')} {material.checksum ? material.checksum : t('none')}</p>
                </details>
                {decodeStatus === 'replaced' ? <p className="muted" style={{ marginTop: 8 }}>{t('decodeReplaced')}</p> : null}
                {material.kind === 'table' ? <TableSummary material={material} t={t} /> : null}
                {material.kind === 'image' ? <ImageSummary material={material} t={t} /> : null}
                {material.notes ? <p className="muted" style={{ marginTop: 8 }}>{material.notes}</p> : null}
                {preview.length > 0 ? (
                  <div className="stack" style={{ marginTop: 12 }}>
                    {preview.map((span) => (
                      <div className={`fact ${spanLooksEmpty(span) ? 'unknown' : 'present'}`} key={span.id}>
                        <div className="fact-label">{t('locator')} {locatorKindLabel(span.locator_kind, t)}</div>
                        <div className="meta-row">
                          <span>{t('page')} {span.page === null ? <NullValue /> : span.page}</span>
                          <span>{t('start')} {span.start_offset === null ? <NullValue /> : span.start_offset}</span>
                          <span>{t('end')} {span.end_offset === null ? <NullValue /> : span.end_offset}</span>
                          {span.sheet ? <span>{t('sheet')} {span.sheet}</span> : null}
                          {span.cell_ref ? <span>{t('cell')} {span.cell_ref}</span> : null}
                          {span.locator_kind === 'region' ? <RegionMeta span={span} t={t} /> : null}
                        </div>
                        {span.excerpt ? <p style={{ marginTop: 8, fontFamily: 'var(--font-display)' }}>{span.excerpt}</p> : null}
                      </div>
                    ))}
                    {spans.length > preview.length ? (
                      <p className="muted">{t('moreSpans')} {spans.length - preview.length}</p>
                    ) : null}
                  </div>
                ) : null}
              </article>
            )
          })}
        </div>
      )}

      <p className="muted" style={{ marginTop: 22 }}>
        {t('evidenceInstructionBoundary')} {' '}
        <Link className="crumb" to="/analyses">{t('backAnalyses')}</Link>
      </p>
    </div>
  )
}
