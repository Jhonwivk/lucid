import { useEffect, useState } from 'react'
import { getMaterialPreview, materialContentUrl } from '../api/client'
import type { Material, MaterialPreview, SourceSpan } from '../api/types'
import { useI18n, type Translate } from '../i18n'
import { formatTimestamp, locatorKindLabel, materialKindLabel } from '../lib/format'
import { Quantity } from './NullValue'

function locatorCopy(precision: string | undefined, t: Translate): string {
  if (precision === 'exact') return t('locatorExact')
  if (precision === 'whole_source') return t('locatorWhole')
  if (precision === 'unresolved') return t('locatorUnresolved')
  return t('locatorApproximate')
}

export type SourceHighlight = {
  start?: number | null
  end?: number | null
  page?: number | null
  sheet?: string | null
  cell?: string | null
  precision?: string | null
}

type SourceViewerProps = {
  projectId: string
  material: Material | null
  spans: SourceSpan[]
  highlight?: SourceHighlight
}

export function SourceViewer({ projectId, material, spans, highlight }: SourceViewerProps) {
  const { locale, t } = useI18n()
  const [preview, setPreview] = useState<MaterialPreview | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!material) return
    let cancelled = false
    getMaterialPreview(projectId, material.id, {
      start: highlight?.start ?? 0,
      end: highlight?.end ?? 4000,
      page: highlight?.page,
      sheet: highlight?.sheet,
      cell: highlight?.cell,
    })
      .then((payload) => {
        if (!cancelled) {
          setPreview(payload)
          setError(null)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : t('unknownError'))
      })
    return () => {
      cancelled = true
    }
  }, [material, projectId, t, highlight?.start, highlight?.end, highlight?.page, highlight?.sheet, highlight?.cell])

  if (!material) {
    return <div className="source-viewer empty">{t('selectSource')}</div>
  }

  const media = material.media_type ?? ''
  const contentUrl = preview?.content_url ?? materialContentUrl(projectId, material.id)
  const isImage = media.startsWith('image/')
  const isPdf = media === 'application/pdf'
  const isText = media.startsWith('text/') || media === 'application/json'
  const excerpt = preview?.excerpt ?? ''
  const windowStart = Number(preview?.locator?.window_start ?? preview?.locator?.start_offset ?? 0)
  const absStart = highlight?.start ?? null
  const absEnd = highlight?.end ?? null
  const canMark =
    isText &&
    absStart != null &&
    absEnd != null &&
    absEnd > absStart &&
    absStart >= windowStart &&
    absStart < windowStart + excerpt.length
  const relStart = canMark ? Math.max(0, absStart! - windowStart) : 0
  const relEnd = canMark ? Math.min(excerpt.length, absEnd! - windowStart) : 0
  const precision = String(highlight?.precision ?? preview?.locator?.precision ?? '')
  const shownPage = highlight?.page ?? (typeof preview?.locator?.page === 'number' ? preview.locator.page : null)

  return (
    <section className="source-viewer" aria-label={t('sourceViewer')}>
      <header>
        <h3>{material.filename}</h3>
        <p className="muted">
          {materialKindLabel(material.kind, t)}
          {shownPage != null ? ` · ${t('locatorPdfPage')} ${shownPage}` : ''}
          {highlight?.sheet ? ` · ${t('sheet')} ${highlight.sheet}` : ''}
          {highlight?.cell ? ` · ${t('cell')} ${highlight.cell}` : ''}
        </p>
        <p className="muted">{locatorCopy(precision, t)}</p>
      </header>
      {error ? <p role="alert">{error}</p> : null}
      {isImage ? (
        <figure>
          <img src={contentUrl} alt={material.filename} />
          <figcaption className="muted">{t('fullImageProvenance')}</figcaption>
        </figure>
      ) : null}
      {isPdf ? (
        <object data={contentUrl} type="application/pdf" className="pdf-frame" aria-label={material.filename}>
          <a href={contentUrl}>{material.filename}</a>
        </object>
      ) : null}
      {isText ? (
        <pre className="source-text">
          {canMark ? (
            <>
              {excerpt.slice(0, relStart)}
              <mark>{excerpt.slice(relStart, relEnd)}</mark>
              {excerpt.slice(relEnd)}
            </>
          ) : (
            excerpt
          )}
        </pre>
      ) : null}
      {!isImage && !isPdf && !isText ? (
        <div className="stack">
          {spans
            .filter((span) => {
              if (highlight?.sheet && span.sheet && span.sheet.toLowerCase() !== highlight.sheet.toLowerCase()) return false
              if (highlight?.cell && span.cell_ref && span.cell_ref.toLowerCase() !== highlight.cell.toLowerCase()) return false
              if (highlight?.page != null && span.page != null && span.page !== highlight.page) return false
              return true
            })
            .slice(0, 24)
            .map((span) => (
              <article className="fact present" key={span.id}>
                <div className="fact-label">{locatorKindLabel(span.locator_kind, t)}</div>
                <p className="muted">
                  {span.sheet ? `${t('sheet')} ${span.sheet}` : ''}
                  {span.cell_ref ? ` · ${t('cell')} ${span.cell_ref}` : ''}
                  {span.page != null ? ` · ${t('page')} ${span.page}` : ''}
                </p>
                {span.excerpt ? <p>{span.excerpt}</p> : <p className="muted">{t('locatorUnresolved')}</p>}
              </article>
            ))}
        </div>
      ) : null}
      {preview?.locator && typeof preview.locator.truncated === 'boolean' && preview.locator.truncated ? (
        <p className="muted">{t('truncatedRead')}</p>
      ) : null}
      {preview?.derived ? <p className="muted">{t('derivedPreview')}</p> : null}
      <details className="tech-details">
        <summary>{t('technicalDetails')}</summary>
        <p>{t('checksum')} {material.checksum ?? t('none')}</p>
        <p><Quantity name={t('bytes')} value={material.byte_size ?? null} /></p>
        <p>{t('recorded')} {formatTimestamp(material.created_at, locale, t)}</p>
        <p>{t('type')} {media || t('unspecified')}</p>
      </details>
    </section>
  )
}
