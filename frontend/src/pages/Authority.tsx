/** Authority workspace: network overview, shortages, transfer network.
 *  Read-only, from precomputed results — no session and no upload.
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Layout } from '../components/Layout'
import {
  CoverageBar,
  ErrorCard,
  Loading,
  Panel,
  Pill,
  Readout,
  coverageTone,
  facilityLabel,
  monthLabel,
  num,
} from '../components/ui'
import {
  ApiError,
  api,
  type AuthorityOverview,
  type AuthorityProduct,
  type AuthorityTransfer,
} from '../lib/api'

const MISSING_HINT = 'Run `python scripts/export_artifacts.py` to build the network results.'

/** Shared loader: authority data is static JSON, so one hook fits all three pages. */
function useAuthority<T>(load: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    load()
      .then((result) => { if (alive) setData(result) })
      .catch((err) => {
        if (!alive) return
        setError(err instanceof ApiError && err.code === 'authority_data_missing' ? MISSING_HINT : String(err?.message ?? err))
      })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return { data, error, loading }
}

export function AuthorityHome() {
  const { data, error, loading } = useAuthority<AuthorityOverview>(() => api.authorityOverview())

  return (
    <Layout
      workspace="authority"
      crumb="Authority oversight"
      title="Network Overview"
      subtitle={data ? `${num(data.facilities)} warehouses · ${data.products} supplies · period ${data.period}` : undefined}
    >
      <section className="statement on-ink">
        <p className="eyebrow">Whole network</p>
        <h2 style={{ marginTop: 'var(--s-3)' }}>
          {data
            ? `${data.kpis.coverage_pct}% of the forecast shortage can be covered by moving stock`
            : 'One network, a clearer picture'}
        </h2>
        {data && (
          <p className="statement-meta">
            {num(Math.round(data.kpis.covered_by_transfers_units))} of{' '}
            {num(Math.round(data.kpis.predicted_shortage_units))} shortage units, without buying anything new
          </p>
        )}
      </section>

      {loading && <Loading label="Loading the network picture…" />}
      {error && <ErrorCard title="Network results not available" message={error} />}

      {data && (
        <>
          {/* Whole units: a tenth of a tablet is noise at network scale. */}
          <Readout
            items={[
              { label: 'Predicted shortage', value: num(Math.round(data.kpis.predicted_shortage_units)), tone: 'critical' },
              { label: 'Covered by transfers', value: num(Math.round(data.kpis.covered_by_transfers_units)), tone: 'surplus' },
              { label: 'Needs buying', value: num(Math.round(data.kpis.needs_procurement_units)), tone: 'at_risk' },
              { label: 'Suggested transfers', value: num(data.kpis.suggested_transfers) },
            ]}
          />

          <div className="split">
            <Panel
              title="What the plan achieves"
              note={
                <>
                  Average transfer distance {num(data.kpis.mean_transfer_distance_km)} km. The remaining{' '}
                  {num(Math.round(data.kpis.needs_procurement_units))} units cannot be sourced from existing
                  surplus and need procurement.
                </>
              }
            >
              <div className="stack" style={{ gap: 6 }}>
                <div className="row-between small">
                  <span className="muted">Deficit covered by redistribution</span>
                  <strong className="mono">{data.kpis.coverage_pct}%</strong>
                </div>
                <CoverageBar pct={data.kpis.coverage_pct} tone={data.kpis.coverage_pct > 60 ? 'surplus' : 'at_risk'} />
              </div>
              <div className="row" style={{ marginTop: 'var(--s-5)' }}>
                <Link className="btn btn-sm btn-primary" to="/authority/shortages">See what needs buying</Link>
              </div>
            </Panel>

            <Panel
              title="Monitoring scope"
              note={`Generated ${new Date(data.generated_at).toLocaleString()}`}
            >
              <ul className="small muted" style={{ margin: 0, paddingLeft: 18, lineHeight: 2 }}>
                <li>{num(data.facilities)} hospital warehouses</li>
                <li>{data.products} essential supplies</li>
                <li>Range hit rate {data.model?.coverage_p10_p90 != null ? `${(data.model.coverage_p10_p90 * 100).toFixed(1)}%` : '—'}</li>
                <li>P50 error {data.model?.p50_mae != null ? `${num(Math.round(data.model.p50_mae))} units` : '—'}</li>
                <li>Tested on {data.model?.test_rows != null ? num(data.model.test_rows) : '—'} unseen records</li>
              </ul>
            </Panel>
          </div>
        </>
      )}
    </Layout>
  )
}

const FILTERS: { id: string; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'needs_buying', label: 'Needs buying' },
  { id: 'partly_covered', label: 'Partly covered' },
  { id: 'fixed_by_transfers', label: 'Fixed by transfers' },
]

const BUCKET_LABEL: Record<string, string> = {
  needs_buying: 'Needs buying',
  partly_covered: 'Partly covered',
  fixed_by_transfers: 'Fixed by transfers',
}

export function AuthorityShortages() {
  const [filter, setFilter] = useState('all')
  const [rows, setRows] = useState<AuthorityProduct[]>([])
  const [selected, setSelected] = useState<AuthorityProduct | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    setLoading(true)
    api
      .authorityProducts(filter)
      .then((result) => {
        if (!alive) return
        setRows(result.products)
        setSelected(result.products[0] ?? null)
        setError(null)
      })
      .catch((err) => {
        if (alive) setError(err instanceof ApiError && err.code === 'authority_data_missing' ? MISSING_HINT : String(err?.message ?? err))
      })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [filter])

  return (
    <Layout
      workspace="authority"
      crumb="Authority oversight"
      title="Shortages & Procurement"
      subtitle="Per-supply coverage across the network"
      actions={
        <div className="row" role="group" aria-label="Filter supplies">
          {FILTERS.map((option) => (
            <button
              key={option.id}
              className={`chip${filter === option.id ? ' on' : ''}`}
              aria-pressed={filter === option.id}
              onClick={() => setFilter(option.id)}
            >
              {option.label}
            </button>
          ))}
        </div>
      }
    >
      {loading && <Loading />}
      {error && <ErrorCard title="Network results not available" message={error} />}

      {!loading && !error && (
        <div className="split">
          <Panel title="Supplies" flush={rows.length > 0}>
            {rows.length === 0 ? (
              <p className="small muted">Nothing in this category.</p>
            ) : (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Supply</th>
                      <th className="num">Shortage</th>
                      <th className="num">Still short</th>
                      <th style={{ width: 132 }}>Coverage</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => (
                      <tr
                        key={row.product_id}
                        className={`selectable${selected?.product_id === row.product_id ? ' on' : ''}`}
                        onClick={() => setSelected(row)}
                      >
                        <td className="cell-title">{row.name}</td>
                        <td className="num">{num(Math.round(row.shortage_units))}</td>
                        <td className="num">{num(Math.round(row.still_short_units))}</td>
                        <td>
                          <CoverageBar pct={row.coverage_pct ?? 0} tone={coverageTone(row.coverage_pct)} />
                          <span className="micro mono muted" style={{ display: 'block', marginTop: 4 }}>
                            {row.coverage_pct != null ? `${row.coverage_pct}%` : '—'}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>

          {selected && (
            <Panel
              title={
                <div>
                  <p className="eyebrow">Supply detail</p>
                  <h2 style={{ marginTop: 4 }}>{selected.name}</h2>
                </div>
              }
              aside={
                <Pill tone={selected.bucket === 'needs_buying' ? 'critical' : selected.bucket === 'partly_covered' ? 'at_risk' : 'ok'}>
                  {BUCKET_LABEL[selected.bucket] ?? selected.bucket}
                </Pill>
              }
              note={
                selected.still_short_units > 0
                  ? `Redistribution closes ${num(Math.round(selected.covered_units))} units. Procure the remaining ${num(Math.round(selected.still_short_units))}.`
                  : 'Existing surplus covers this shortage entirely — no procurement needed.'
              }
            >
              <Readout
                items={[
                  { label: 'Shortage', value: num(Math.round(selected.shortage_units)), tone: 'critical' },
                  { label: 'Covered', value: num(Math.round(selected.covered_units)), tone: 'surplus' },
                  { label: 'Still short', value: num(Math.round(selected.still_short_units)), tone: 'at_risk' },
                  { label: 'Network surplus', value: num(Math.round(selected.surplus_units)) },
                ]}
              />
            </Panel>
          )}
        </div>
      )}
    </Layout>
  )
}

export function AuthorityTransfers() {
  const { data, error, loading } = useAuthority<{ transfers: AuthorityTransfer[] }>(() => api.authorityTransfers(30))
  const transfers = data?.transfers ?? []

  const totalUnits = transfers.reduce((sum, t) => sum + t.units, 0)
  const far = transfers.filter((t) => t.far).length

  // Simple equirectangular projection of donor/receiver points — enough to
  // show geographic spread without pulling in a map library.
  const points = transfers.flatMap((t) => [
    { lat: t.donor_lat, lon: t.donor_long, kind: 'donor' as const },
    { lat: t.receiver_lat, lon: t.receiver_long, kind: 'receiver' as const },
  ]).filter((p): p is { lat: number; lon: number; kind: 'donor' | 'receiver' } => p.lat != null && p.lon != null)

  const lats = points.map((p) => p.lat)
  const lons = points.map((p) => p.lon)
  const bounds = points.length
    ? { minLat: Math.min(...lats), maxLat: Math.max(...lats), minLon: Math.min(...lons), maxLon: Math.max(...lons) }
    : null

  return (
    <Layout workspace="authority" crumb="Authority oversight" title="Transfer Network" subtitle="The largest moves in the optimised plan">
      {loading && <Loading />}
      {error && <ErrorCard title="Network results not available" message={error} />}

      {!loading && !error && (
        <>
          <Readout
            items={[
              { label: 'Transfers shown', value: num(transfers.length) },
              { label: 'Units moved', value: num(Math.round(totalUnits)) },
              { label: 'Over 50 km', value: num(far), tone: far > 0 ? 'at_risk' : undefined },
            ]}
          />

          <div className="split">
            <Panel title="Largest transfers" flush>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr><th>Supply</th><th>Route</th><th className="num">Units</th><th className="num">Distance</th></tr>
                  </thead>
                  <tbody>
                    {transfers.map((transfer, index) => (
                      <tr key={`${transfer.product_id}-${transfer.donor_facility_id}-${transfer.receiver_facility_id}-${index}`}>
                        <td>
                          <div className="cell-title">{transfer.name}</div>
                          <div className="cell-sub">{monthLabel(transfer.month)}</div>
                        </td>
                        <td className="micro">
                          {facilityLabel({ id: transfer.donor_facility_id, district: transfer.donor_district, facility_type: transfer.donor_facility_type })}
                          <span style={{ color: 'var(--gold-600)' }}> → </span>
                          {facilityLabel({ id: transfer.receiver_facility_id, district: transfer.receiver_district, facility_type: transfer.receiver_facility_type })}
                        </td>
                        <td className="num" style={{ fontWeight: 600, color: 'var(--text-900)' }}>{num(transfer.units)}</td>
                        <td className="num">
                          {num(transfer.distance_km)} km {transfer.far && <Pill tone="at_risk">Far</Pill>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>

            <Panel
              title="Donor map"
              note="Positions are a simple lat/long projection of the facilities in the table, for spread only — not a routing map."
            >
              {bounds ? (
                <div
                  className="map"
                  style={{ height: 320 }}
                  role="img"
                  aria-label={`${points.length} facilities involved in the largest transfers`}
                >
                  {points.map((point, index) => {
                    const x = ((point.lon - bounds.minLon) / (bounds.maxLon - bounds.minLon || 1)) * 90 + 5
                    const y = 95 - ((point.lat - bounds.minLat) / (bounds.maxLat - bounds.minLat || 1)) * 90
                    return (
                      <span
                        key={index}
                        className="map-dot"
                        style={{
                          left: `${x}%`,
                          top: `${y}%`,
                          background: point.kind === 'donor' ? 'var(--surplus)' : 'var(--critical)',
                        }}
                      />
                    )
                  })}
                </div>
              ) : (
                <p className="small muted">No coordinates available for these transfers.</p>
              )}
              <div className="row micro muted" style={{ marginTop: 'var(--s-3)', gap: 'var(--s-4)' }}>
                <span className="row" style={{ gap: 6 }}>
                  <span style={{ width: 7, height: 7, borderRadius: '50%', background: 'var(--surplus)' }} /> donor
                </span>
                <span className="row" style={{ gap: 6 }}>
                  <span style={{ width: 7, height: 7, borderRadius: '50%', background: 'var(--critical)' }} /> receiver
                </span>
              </div>
            </Panel>
          </div>
        </>
      )}
    </Layout>
  )
}
