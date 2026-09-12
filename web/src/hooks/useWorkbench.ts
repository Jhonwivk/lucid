import { useCallback, useEffect, useState } from 'react'
import { errorMessage, loadWorkbench } from '../api/client'
import type { LoadState, WorkbenchData } from '../api/types'
import { useI18n } from '../i18n'

export function useWorkbench(projectId: string | undefined) {
  const { t } = useI18n()
  const missing = !projectId
  const [state, setState] = useState<LoadState>(missing ? 'error' : 'loading')
  const [data, setData] = useState<WorkbenchData | null>(null)
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(async () => {
    if (!projectId) return
    try {
      const payload = await loadWorkbench(projectId)
      setData(payload)
      setError(null)
      setState('ready')
    } catch (err) {
      setData(null)
      setError(errorMessage(err))
      setState('error')
    }
  }, [projectId])

  useEffect(() => {
    if (!projectId) {
      return
    }

    const id = projectId
    let cancelled = false

    async function load() {
      try {
        const payload = await loadWorkbench(id)
        if (!cancelled) {
          setData(payload)
          setError(null)
          setState('ready')
        }
      } catch (err) {
        if (!cancelled) {
          setData(null)
          setError(errorMessage(err))
          setState('error')
        }
      }
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [projectId])

  if (missing) {
    return {
      state: 'error' as LoadState,
      data: null,
      error: t('missingAnalysisId'),
      reload,
    }
  }

  return { state, data, error, reload }
}
