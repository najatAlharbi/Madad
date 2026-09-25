/** Forecasted Needs — the supply list on the left, the selected supply's
 *  forecast on the right. Every number here comes from /api/forecast/results.
 */
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ForecastChart } from '../components/ForecastChart'
import { Layout } from '../components/Layout'
import {
  AiNote,
  CoverageMeter,
  ErrorCard,
  Loading,
  Panel,
  Pill,
  Readout,
  StatusPill,
  facilityLabel,
  monthLabel,
  num,
} from '../components/ui'
import { useForecast } from '../hooks/useForecast'

export default function Forecasts() {
  const { run, loading, missing, error } = useForecast()
  const [view, setView] = useState<'act' | 'all'>('act')
  const [selectedId, setSelectedId] = useState<number | null>(null)

  const needAction = useMemo(() => run?.products.filter((p) => p.gap > 0) ?? [], [run])
  const list = view === 'act' ? needAction : (run?.products ?? [])
  const selected = useMemo(
    () => list.find((p) => p.product_id === selectedId) ?? list[0] ?? null,
    [list, selectedId],
  )

  const facilityLine = run ? facilityLabel(run.facility) : undefined

  return (
    <Layout
      workspace="warehouse"
      crumb="Warehouse operations"
      title="Forecasted Needs"
      subtitle={run ? monthLabel(run.forecast_month) : undefined}
      isDemo={run?.is_demo}
      facilityLabel={facilityLine}
    >
      {loading && <Loading label="Running the models…" />}
      {error && <ErrorCard title="Could not load the forecast" message={error} />}

      {missing && !loading && (
        <Panel title="No forecast yet">
          <p className="small muted">Add a month of stock data first.</p>
          <div className="row" style={{ marginTop: 'var(--s-4)' }}>
            <Link className="btn btn-primary" to="/warehouse/upload">Go to upload</Link>
          </div>
        </Panel>
      )}

      {run && selected && (
        <div className="picker">
          <Panel
            title="Supplies"
            flush
            aside={
              <div className="seg" role="group" aria-label="Which supplies to show">
                <button className={view === 'act' ? 'on' : ''} aria-pressed={view === 'act'} onClick={() => setView('act')}>
                  Need action ({needAction.length})
                </button>
                <button className={view === 'all' ? 'on' : ''} aria-pressed={view === 'all'} onClick={() => setView('all')}>
                  All ({run.products.length})
                </button>
              </div>
            }
          >
            <div className="ledger scroll-y" style={{ maxHeight: 560 }}>
              {list.length === 0 && (
                <p className="small muted" style={{ padding: 'var(--s-5)' }}>Nothing needs action this month.</p>
              )}
              {list.map((product) => (
                <button
                  key={product.product_id}
                  className={`ledger-row${product.product_id === selected.product_id ? ' on' : ''}`}
                  aria-pressed={product.product_id === selected.product_id}
                  onClick={() => setSelectedId(product.product_id)}
                >
                  <span style={{ minWidth: 0 }}>
                    <span className="ledger-name">{product.name}</span>
                    <span className="ledger-sub">
                      {product.gap > 0
                        ? <>Get <span className="mono">{num(product.gap)}</span> units</>
                        : <><span className="mono">{num(product.stock)}</span> in stock</>}
                    </span>
                    <span style={{ display: 'block', marginTop: 'var(--s-3)' }}>
                      <CoverageMeter
                        stock={product.stock}
                        p10={product.p10}
                        p50={product.p50}
                        p90={product.p90}
                        tone={product.severity}
                      />
                    </span>
                  </span>
                  <span style={{ justifySelf: 'end' }}><StatusPill severity={product.severity} /></span>
                </button>
              ))}
            </div>
          </Panel>

          <div className="stack" style={{ gap: 'var(--s-5)' }}>
            <Panel
              labelledBy="fcTitle"
              title={
                <div style={{ minWidth: 0 }}>
                  <p className="eyebrow">XGBoost quantile forecast</p>
                  <h2 id="fcTitle" style={{ marginTop: 4 }}>{selected.name}</h2>
                </div>
              }
              aside={
                <div className="row" style={{ gap: 'var(--s-2)' }}>
                  {selected.low_confidence && <Pill tone="at_risk">Low confidence — no recent history</Pill>}
                  <StatusPill severity={selected.severity} />
                </div>
              }
            >
              <ForecastChart history={selected.history} stock={selected.stock} productName={selected.name} />

              <div className="stack" style={{ marginTop: 'var(--s-5)', gap: 'var(--s-3)' }}>
                <div className="quantiles">
                  <div className="q-cell">
                    <div className="q-label">Low · P10</div>
                    <div className="q-value">{num(selected.p10)}</div>
                  </div>
                  <div className="q-cell q-mid">
                    <div className="q-label">Expected · P50</div>
                    <div className="q-value">{num(selected.p50)}</div>
                  </div>
                  <div className="q-cell">
                    <div className="q-label">High · P90</div>
                    <div className="q-value">{num(selected.p90)}</div>
                  </div>
                </div>

                <div className={`verdict ${selected.gap > 0 ? 'is-short' : 'is-ok'}`}>
                  <div>
                    <div className="verdict-label">{selected.gap > 0 ? 'Gap to cover' : 'Spare stock'}</div>
                    <p className="small" style={{ marginTop: 4 }}>
                      <span className="mono">{num(selected.stock)}</span> units on hand against a P90 of{' '}
                      <span className="mono">{num(selected.p90)}</span>
                    </p>
                  </div>
                  <div className="verdict-value">{num(selected.gap > 0 ? selected.gap : selected.surplus)}</div>
                </div>
              </div>
            </Panel>

            <Panel
              title="Model quality"
              aside={<span className="micro muted">Measured on unseen months</span>}
              note={
                <>
                  The range is an 80% interval: in testing, actual consumption fell inside P10–P90 about{' '}
                  {run.model.coverage != null ? `${(run.model.coverage * 100).toFixed(0)}%` : '80'}% of the time.
                  Plan against P90 when a stockout is costly. MSE penalises large misses harder than MAE
                  does — a useful second view, since a model can have a low average error and still miss
                  badly on a few supplies.
                </>
              }
            >
              <Readout
                items={[
                  {
                    label: 'Range hit rate',
                    value: run.model.coverage != null ? `${(run.model.coverage * 100).toFixed(1)}%` : '—',
                  },
                  {
                    label: 'P50 error (MAE)',
                    value: run.model.p50_mae != null ? num(Math.round(run.model.p50_mae)) : '—',
                    unit: run.model.p50_mae != null ? 'units' : undefined,
                  },
                  {
                    label: 'Mean squared error',
                    value: run.model.p50_mse != null ? num(Math.round(run.model.p50_mse)) : '—',
                  },
                  {
                    label: 'Tested on',
                    value: run.model.test_rows != null ? num(run.model.test_rows) : '—',
                    unit: run.model.test_rows != null ? 'records' : undefined,
                  },
                ]}
              />
            </Panel>

            <AiNote
              action={
                <>
                  <Link className="btn btn-sm" to="/warehouse/chat">Ask about it</Link>
                  {selected.gap > 0 && <Link className="btn btn-sm btn-primary" to="/warehouse/transfers">Find donors</Link>}
                </>
              }
            >
              {selected.gap > 0
                ? `${selected.name} is ${selected.severity === 'critical' ? 'critical' : 'at risk'}: ${num(selected.stock)} units on hand against a P90 of ${num(selected.p90)}, so get ${num(selected.gap)} units.`
                : `${selected.name} has enough: ${num(selected.stock)} units on hand covers the P90 of ${num(selected.p90)}.`}
            </AiNote>
          </div>
        </div>
      )}
    </Layout>
  )
}
