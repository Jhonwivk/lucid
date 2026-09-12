import { useCallback, useEffect, useRef, useState } from 'react'
import { errorMessage, loadWorkbench } from '../api/client'
import type { LoadState, WorkbenchData } from '../api/types'
import { useI18n } from '../i18n'

export function useWorkbench(projectId: string | undefined) {
  const { t } = useI18n()
  const missing = !projectId
  const [state, setState] = useState<LoadState>(missing ? 'error' : 'loading')
  const [data, setData] = useState<WorkbenchData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [stale, setStale] = useState(false)
  const dataRef = useRef<WorkbenchData | null>(null)

  const reload = useCallback(async () => {
    if (!projectId) return
    try {
      const payload = await loadWorkbench(projectId)
      dataRef.current = payload
      setData(payload)
      setError(null)
      setStale(false)
      setState('ready')
    } catch (err) {
      setError(errorMessage(err))
      const previous = dataRef.current
      if (previous && previous.project.id === projectId) {
        setStale(true)
        setState('ready')
        return
      }
      setStale(false)
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
          dataRef.current = payload
          setData(payload)
          setError(null)
          setStale(false)
          setState('ready')
        }
      } catch (err) {
        if (!cancelled) {
          setError(errorMessage(err))
          const previous = dataRef.current
          if (previous && previous.project.id === id) {
            setStale(true)
            setState('ready')
            return
          }
          setStale(false)
          setData(null)
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
      stale: false,
      reload,
    }
  }

  return { state, data, error, stale, reload }
}
