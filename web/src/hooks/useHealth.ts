import { useEffect, useState } from 'react'
import { errorMessage, getHealth } from '../api/client'
import type { HealthPayload, LoadState } from '../api/types'

export function useHealth() {
  const [state, setState] = useState<LoadState>('loading')
  const [health, setHealth] = useState<HealthPayload | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function load() {
      try {
        const payload = await getHealth()
        if (!cancelled) {
          setHealth(payload)
          setError(null)
          setState('ready')
        }
      } catch (err) {
        if (!cancelled) {
          setHealth(null)
          setError(errorMessage(err))
          setState('error')
        }
      }
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [])

  return { state, health, error }
}
