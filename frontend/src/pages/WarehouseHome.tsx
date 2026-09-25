/** My Warehouse — the month's verdict first, then what to do about it.
 *
 *  Layout follows the content: one statement (the month's headline), one
 *  measurement strip (the counts, which compare best side by side), then a
 *  ledger of the actual actions. No repeated card grid.
 */
import { Link } from 'react-router-dom'
import { Layout } from '../components/Layout'
import {
  AiNote,
  CoverageMeter,
  ErrorCard,
  Loading,
  Panel,
  Readout,
  StatusPill,
  facilityLabel,
  monthLabel,
  num,
} from '../components/ui'
import { useForecast } from '../hooks/useForecast'

export default function WarehouseHome() {
  const { run, loading, missing, error } = useForecast()

  const facilityLine = run ? facilityLabel(run.facility) : undefined

  const actions = run ? [...run.products].filter((p) => p.gap > 0).sort((a, b) => b.gap - a.gap).slice(0, 5) : []

  const headline = !run
    ? 'Load a month to see what you will need'
    : run.counts.critical > 0
      ? `${run.counts.critical} ${run.counts.critical === 1 ? 'supply may' : 'supplies may'} run out in ${monthLabel(run.forecast_month)}`
      : `Nothing critical in ${monthLabel(run.forecast_month)}`

  return (
    <Layout
      workspace="warehouse"
      crumb="Warehouse operations"
      title="My Warehouse"
      subtitle={run ? `Forecast for ${monthLabel(run.forecast_month)}, from ${monthLabel(run.source_month)} stock` : undefined}
      isDemo={run?.is_demo}
      facilityLabel={facilityLine}
    >
      <section className="statement on-ink">
        <p className="eyebrow">This month</p>
        <h2 style={{ marginTop: 'var(--s-3)' }}>{headline}</h2>
        {run && (
          <p className="statement-meta">
            {run.counts.at_risk} at risk · {run.counts.surplus} with spare stock · {run.counts.total} supplies tracked
          </p>
        )}
        <div className="row" style={{ marginTop: 'var(--s-6)' }}>
          <Link className="btn btn-on-ink" to="/warehouse/forecasts">Review forecasts</Link>
          <Link className="btn btn-ghost-ink" to="/warehouse/upload">Upload next month</Link>
        </div>
      </section>

      {loading && <Loading label="Loading your forecast…" />}
      {error && <ErrorCard title="Could not load the forecast" message={error} />}

      {missing && !loading && (
        <Panel title="No forecast yet">
          <p className="small muted">
            Upload a month of stock data, or load the sample facility to see the whole flow.
          </p>
          <div className="row" style={{ marginTop: 'var(--s-4)' }}>
            <Link className="btn btn-primary" to="/warehouse/upload">Add your month</Link>
          </div>
        </Panel>
      )}

      {run && (
        <>
          <Readout
            items={[
              { label: 'Supplies tracked', value: num(run.counts.total) },
              { label: 'Critical', value: num(run.counts.critical), tone: 'critical' },
              { label: 'At risk', value: num(run.counts.at_risk), tone: 'at_risk' },
              { label: 'Spare stock', value: num(run.counts.surplus), tone: 'surplus' },
            ]}
          />

          {run.counts.critical > 0 && (
            <div className="urgent">
              <div>
                <strong>Need a critical supply now?</strong>
                <div className="small muted">Find the nearest warehouse that can send it today.</div>
              </div>
              <Link className="btn btn-danger" to="/warehouse/transfers">Emergency request</Link>
            </div>
          )}

          <Panel
            title="What to do this month"
            aside={<Link className="btn btn-sm" to="/warehouse/transfers">Find donors</Link>}
            note={
              actions.length > 0
                ? 'Gaps are measured against P90 — the high end of the forecast range — so covering them protects against a bad month, not just an average one.'
                : undefined
            }
            flush={actions.length > 0}
          >
            {actions.length === 0 ? (
              <p className="small muted">
                Nothing needs action — every supply has enough stock for the high (P90) forecast.
              </p>
            ) : (
              <div className="ledger">
                {actions.map((product) => (
                  <div key={product.product_id} className="ledger-row" style={{ cursor: 'default' }}>
                    <span style={{ minWidth: 0 }}>
                      <span className="row" style={{ gap: 'var(--s-2)' }}>
                        <StatusPill severity={product.severity} />
                        <span className="ledger-name">{product.name}</span>
                      </span>
                      <span className="ledger-sub">
                        Get <span className="mono">{num(product.gap)}</span> units ·{' '}
                        <span className="mono">{num(product.stock)}</span> in stock, needs up to{' '}
                        <span className="mono">{num(product.p90)}</span>
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
                    <Link className="btn btn-sm" to="/warehouse/forecasts">View</Link>
                  </div>
                ))}
              </div>
            )}
          </Panel>

          <AiNote action={<Link className="btn btn-sm" to="/warehouse/chat">Ask about this month</Link>}>
            {run.counts.critical > 0
              ? `${run.counts.critical} supplies are below their expected demand for ${monthLabel(run.forecast_month)}. The largest single gap is ${num(actions[0]?.gap)} units of ${actions[0]?.name}.`
              : `No supply is below its expected demand for ${monthLabel(run.forecast_month)}.`}
          </AiNote>
        </>
      )}
    </Layout>
  )
}
