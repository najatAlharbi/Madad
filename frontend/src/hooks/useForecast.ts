/** Shared forecast state.
 *
 * Several warehouse screens need the same run, so it is fetched once here
 * and shared through context rather than re-requested per page. A 410 flips
 * `expired`, which the shell renders as the session-expired screen.
 */
import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { ApiError, SessionExpiredError, api, type ForecastRun } from '../lib/api'

export interface ForecastState {
  run: ForecastRun | null
  loading: boolean
  /** No forecast has been generated yet (HTTP 409) — not an error. */
  missing: boolean
  error: string | null
  expired: boolean
  reload: () => Promise<void>
  runForecast: () => Promise<ForecastRun | null>
}

export const ForecastContext = createContext<ForecastState | null>(null)

export function useForecastState(): ForecastState {
  const [run, setRun] = useState<ForecastRun | null>(null)
  const [loading, setLoading] = useState(true)
  const [missing, setMissing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [expired, setExpired] = useState(false)

  const handle = useCallback((err: unknown) => {
    if (err instanceof SessionExpiredError) {
      setExpired(true)
      return
    }
    if (err instanceof ApiError && err.code === 'no_forecast') {
      setMissing(true)
      return
    }
    setError(err instanceof Error ? err.message : String(err))
  }, [])

  const reload = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await api.forecastResults()
      setRun(result)
      setMissing(false)
    } catch (err) {
      setRun(null)
      handle(err)
    } finally {
      setLoading(false)
    }
  }, [handle])

  const runForecast = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await api.runForecast()
      setRun(result)
      setMissing(false)
      return result
    } catch (err) {
      handle(err)
      return null
    } finally {
      setLoading(false)
    }
  }, [handle])

  useEffect(() => {
    void reload()
  }, [reload])

  return { run, loading, missing, error, expired, reload, runForecast }
}

export function useForecast(): ForecastState {
  const context = useContext(ForecastContext)
  if (!context) throw new Error('useForecast must be used inside the warehouse workspace')
  return context
}
