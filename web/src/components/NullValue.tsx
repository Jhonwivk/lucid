import { useI18n } from '../i18n'

type NullValueProps = { label?: string }

export function NullValue({ label }: NullValueProps) {
  const { t } = useI18n()
  return <span className="null-mark">{label ?? t('unknown')}</span>
}

export function Quantity({ value, name }: { value: number | boolean | null; name: string }) {
  const { t } = useI18n()
  if (value === null) return <span>{name}: <NullValue /></span>
  if (typeof value === 'boolean') return <span>{name}: {value ? t('true') : t('false')}</span>
  return <span>{name}: {String(value)}</span>
}
