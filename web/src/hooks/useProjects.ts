import { useCallback, useEffect, useState } from 'react'
import {
  createProject,
  errorMessage,
  listProjects,
  seedDemoProject,
} from '../api/client'
import type { LoadState, ProjectCreate, ProjectSummary } from '../api/types'

export function useProjects() {
  const [state, setState] = useState<LoadState>('loading')
  const [projects, setProjects] = useState<ProjectSummary[]>([])
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(async () => {
    setError(null)
    try {
      const rows = await listProjects()
      setProjects(rows)
      setState('ready')
    } catch (err) {
      setProjects([])
      setError(errorMessage(err))
      setState('error')
    }
  }, [])

  useEffect(() => {
    let cancelled = false

    async function load() {
      try {
        const rows = await listProjects()
        if (!cancelled) {
          setProjects(rows)
          setError(null)
          setState('ready')
        }
      } catch (err) {
        if (!cancelled) {
          setProjects([])
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

  const create = useCallback(async (payload: ProjectCreate) => {
    const created = await createProject(payload)
    setProjects((current) => {
      const without = current.filter((item) => item.id !== created.id)
      return [created, ...without]
    })
    return created
  }, [])

  const seedDemo = useCallback(async () => {
    const demo = await seedDemoProject()
    setProjects((current) => {
      const without = current.filter((item) => item.id !== demo.id)
      return [demo, ...without]
    })
    return demo
  }, [])

  const retry = useCallback(async () => {
    setState('loading')
    await reload()
  }, [reload])

  return { state, projects, error, reload: retry, create, seedDemo }
}
