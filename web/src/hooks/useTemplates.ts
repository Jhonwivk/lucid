import { useCallback, useEffect, useState } from 'react'
import { errorMessage, instantiateTemplate, listTemplates } from '../api/client'
import type { LoadState, TemplateSummary } from '../api/types'

export function useTemplates() {
  const [state, setState] = useState<LoadState>('loading')
  const [templates, setTemplates] = useState<TemplateSummary[]>([])
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const rows = await listTemplates()
      setTemplates(rows)
      setError(null)
      setState('ready')
    } catch (err) {
      setTemplates([])
      setError(errorMessage(err))
      setState('error')
    }
  }, [])

  useEffect(() => {
    let active = true
    listTemplates()
      .then((rows) => {
        if (!active) return
        setTemplates(rows)
        setError(null)
        setState('ready')
      })
      .catch((err) => {
        if (!active) return
        setTemplates([])
        setError(errorMessage(err))
        setState('error')
      })
    return () => {
      active = false
    }
  }, [])

  const instantiate = useCallback(async (templateId: string) => {
    return instantiateTemplate(templateId)
  }, [])

  return { state, templates, error, retry: load, instantiate }
}
