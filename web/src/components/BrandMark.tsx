import { Link } from 'react-router-dom'
import { useI18n } from '../i18n'

type BrandMarkProps = {
  subtle?: string
  to?: string
}

export function BrandMark({ subtle, to }: BrandMarkProps) {
  const { t } = useI18n()
  const content = (
    <>
      <span className="brand-glyph" aria-hidden>
        <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
          <path d="M9 4v20" stroke="currentColor" strokeWidth="1.6" />
          <path d="M13.5 6v16" stroke="currentColor" strokeWidth="1.6" />
          <path d="M9 10h12" stroke="currentColor" strokeWidth="1.2" />
          <path d="M13.5 18h8" stroke="currentColor" strokeWidth="1.2" />
        </svg>
      </span>
      <span className="brand-word">
        LUCID
        {subtle ? <span>{subtle}</span> : null}
      </span>
    </>
  )

  if (to) {
    return (
      <Link className="brand-mark" to={to} aria-label={t('homeAria')}>
        {content}
      </Link>
    )
  }

  return <div className="brand-mark">{content}</div>
}
