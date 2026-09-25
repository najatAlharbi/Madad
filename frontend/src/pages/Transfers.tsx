/** Get & Share Stock — LP-chosen donors per shortage, plus emergency search. */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Layout } from '../components/Layout'
import {
  CoverageBar,
  ErrorCard,
  Loading,
  Panel,
  Pill,
  Spinner,
  StatusPill,
  coverageTone,
  facilityLabel,
  monthLabel,
  num,
} from '../components/ui'
import { useForecast } from '../hooks/useForecast'
import { SessionExpiredError, api, type NearestOption, type TransfersResponse } from '../lib/api'

type Tab = 'need' | 'emergency'

export default function Transfers() {
  const { run } = useForecast()
  const [tab, setTab] = useState<Tab>('need')
  const [data, setData] = useState<TransfersResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [requested, setRequested] = useState<Record<string, boolean>>({})

  useEffect(() => {
    let alive = true
    setLoading(true)
    api
      .transfers(150)
      .then((result) => { if (alive) { setData(result); setError(null) } })
      .catch((err) => {
        if (!alive) return
        if (err instanceof SessionExpiredError) setError('Your session expired — please generate the forecast again.')
        else setError(err instanceof Error ? err.message : String(err))
      })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [])

  const totalDonors = data?.suggestions.reduce((sum, s) => sum + s.donors.length, 0) ?? 0

  return (
    <Layout
      workspace="warehouse"
      crumb="Warehouse operations"
      title="Get & Share Stock"
      subtitle={data ? `${monthLabel(data.month)} · optimised for shortest total distance` : undefined}
      isDemo={run?.is_demo}
      actions={
        <div className="seg" role="group" aria-label="View">
          <button className={tab === 'need' ? 'on' : ''} aria-pressed={tab === 'need'} onClick={() => setTab('need')}>
            What you need {totalDonors ? `(${totalDonors})` : ''}
          </button>
          <button className={tab === 'emergency' ? 'on' : ''} aria-pressed={tab === 'emergency'} onClick={() => setTab('emergency')}>
            Emergency request
          </button>
        </div>
      }
    >
      {error && (
        <ErrorCard
          title="Could not load transfers"
          message={error}
          action={<Link className="btn btn-sm" to="/warehouse/upload">Back to upload</Link>}
        />
      )}

      {tab === 'need' && (
        <>
          {loading && <Loading label="Solving the transfer plan…" />}

          {data && data.suggestions.length === 0 && (
            <Panel title="Nothing to request">
              <p className="small muted">{data.message ?? 'No shortages forecast for this month.'}</p>
            </Panel>
          )}

          {data?.suggestions.map((suggestion) => (
            <Panel
              key={suggestion.product_id}
              flush={suggestion.donors.length > 0}
              title={
                <div style={{ minWidth: 0 }}>
                  <div className="row" style={{ gap: 'var(--s-2)' }}>
                    <StatusPill severity={suggestion.severity} />
                    <h2>{suggestion.name}</h2>
                  </div>
                  <p className="small muted" style={{ marginTop: 4 }}>
                    Need <span className="mono">{num(suggestion.gap)}</span> units ·{' '}
                    <span className="mono">{num(suggestion.covered_units)}</span> available nearby
                    {suggestion.still_short > 0 && <> · <span className="mono">{num(suggestion.still_short)}</span> still short</>}
                  </p>
                </div>
              }
              aside={
                <div style={{ minWidth: 148 }}>
                  <div className="row-between micro muted">
                    <span>coverable</span>
                    <span className="mono" style={{ color: 'var(--text-900)' }}>
                      {suggestion.coverage_pct != null ? `${suggestion.coverage_pct}%` : '—'}
                    </span>
                  </div>
                  <div style={{ marginTop: 6 }}>
                    <CoverageBar pct={suggestion.coverage_pct ?? 0} tone={coverageTone(suggestion.coverage_pct)} />
                  </div>
                </div>
              }
            >
              {suggestion.donors.length === 0 ? (
                <p className="small muted">
                  No warehouse within range has spare stock of this supply — it needs procurement.
                </p>
              ) : (
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Warehouse</th>
                        <th className="num">Spare</th>
                        <th className="num">Send</th>
                        <th className="num">Distance</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {suggestion.donors.map((donor) => {
                        const key = `${suggestion.product_id}-${donor.donor_facility_id}`
                        return (
                          <tr key={key}>
                            <td className="cell-title">{facilityLabel({ id: donor.donor_facility_id, ...donor })}</td>
                            <td className="num">{num(donor.spare_units)}</td>
                            <td className="num" style={{ fontWeight: 600, color: 'var(--text-900)' }}>{num(donor.suggested_units)}</td>
                            <td className="num">
                              {num(donor.distance_km)} km {donor.far && <Pill tone="at_risk">Far</Pill>}
                            </td>
                            <td style={{ textAlign: 'right' }}>
                              <button
                                className={`btn btn-sm${requested[key] ? '' : ' btn-primary'}`}
                                onClick={() => setRequested({ ...requested, [key]: true })}
                                disabled={requested[key]}
                              >
                                {requested[key] ? 'Requested' : 'Request'}
                              </button>
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </Panel>
          ))}

          {data && (
            <p className="micro muted" style={{ maxWidth: '72ch', lineHeight: 1.6 }}>
              Plan parameters: minimum shipment {num(data.parameters.min_transfer_qty)} units, maximum
              distance {data.parameters.max_distance_km != null ? `${num(data.parameters.max_distance_km)} km` : 'unlimited'}.
              Requests are not sent anywhere in this MVP — the button records intent locally.
            </p>
          )}
        </>
      )}

      {tab === 'emergency' && <Emergency />}
    </Layout>
  )
}

function Emergency() {
  const { run } = useForecast()
  const [productId, setProductId] = useState<number | null>(null)
  const [quantity, setQuantity] = useState(50)
  const [options, setOptions] = useState<NearestOption[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const products = run?.products ?? []

  async function search() {
    if (productId == null) return
    setBusy(true)
    setError(null)
    try {
      const result = await api.nearest(productId, quantity)
      setOptions(result.options)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="split">
      <Panel
        title="Emergency request"
        note="Stock figures are each warehouse's latest recorded balance, not a live count."
      >
        <div className="stack">
          <p className="small muted">
            Find the nearest warehouses whose latest recorded stock can cover the amount you need now.
          </p>

          <label>
            <span className="field-label">Supply</span>
            <select className="select" value={productId ?? ''} onChange={(e) => setProductId(Number(e.target.value))}>
              <option value="">— choose a supply —</option>
              {products.map((product) => (
                <option key={product.product_id} value={product.product_id}>{product.name}</option>
              ))}
            </select>
          </label>

          <label>
            <span className="field-label">Units needed</span>
            <input className="input" type="number" min={1} value={quantity} onChange={(e) => setQuantity(Number(e.target.value))} />
          </label>

          <div className="row">
            <button className="btn btn-danger" onClick={search} disabled={busy || productId == null}>
              {busy ? 'Searching…' : 'Find nearest stock'}
            </button>
            {busy && <Spinner label="Checking the network…" />}
          </div>
          {error && <p className="small" style={{ color: 'var(--critical-fg)' }}>{error}</p>}
        </div>
      </Panel>

      <Panel title="Nearest warehouses" flush={!!options?.length}>
        {options == null && <p className="small muted">Choose a supply and a quantity to search.</p>}
        {options?.length === 0 && (
          <p className="small muted">
            No warehouse in the dataset has that much on hand. This supply needs procurement.
          </p>
        )}
        {options && options.length > 0 && (
          <div className="table-scroll">
            <table>
              <thead>
                <tr><th>Warehouse</th><th className="num">On hand</th><th className="num">Distance</th></tr>
              </thead>
              <tbody>
                {options.map((option) => (
                  <tr key={option.donor_facility_id}>
                    <td>
                      <div className="cell-title">{facilityLabel({ id: option.donor_facility_id, ...option })}</div>
                      <div className="cell-sub">as of {monthLabel(option.as_of_month)}</div>
                    </td>
                    <td className="num">{num(option.stock_on_hand)}</td>
                    <td className="num">{num(option.distance_km)} km</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  )
}
