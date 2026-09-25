/** Warehouse workspace wrapper: owns the shared forecast state and renders
 *  the session-expired screen for the whole workspace in one place.
 */
import { Link, Outlet, useNavigate } from 'react-router-dom'
import { ForecastContext, useForecastState } from '../hooks/useForecast'

export default function WarehouseShell() {
  const state = useForecastState()
  const navigate = useNavigate()

  if (state.expired) {
    return (
      <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', padding: 'var(--s-6)' }}>
        <div className="panel rise" style={{ maxWidth: 560 }} role="alert">
          <div className="panel-body stack">
            <span className="tag tag-at_risk">Session expired</span>
            <h1 style={{ fontSize: 'var(--t-hero)' }}>Your session expired</h1>
            <p className="small muted">
              Madad keeps your uploaded month in memory only, for 60 minutes, and clears it when the
              backend restarts. Nothing was saved to a database — generate the forecast again to carry on.
            </p>
            <div className="row" style={{ marginTop: 'var(--s-2)' }}>
              <button className="btn btn-primary" onClick={() => navigate('/warehouse/upload')}>
                Back to upload
              </button>
              <Link className="btn" to="/">Start over</Link>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <ForecastContext.Provider value={state}>
      <Outlet />
    </ForecastContext.Provider>
  )
}
