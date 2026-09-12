import { useI18n } from '../i18n'

export function LanguageToggle() {
  const { locale, setLocale, t } = useI18n()
  return (
    <div className="language-toggle" role="group" aria-label={t('language')}>
      <button type="button" aria-pressed={locale === 'en'} onClick={() => setLocale('en')}>
        {t('english')}
      </button>
      <button type="button" aria-pressed={locale === 'zh-CN'} onClick={() => setLocale('zh-CN')}>
        {t('chinese')}
      </button>
    </div>
  )
}
