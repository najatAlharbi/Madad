/** Upload Data — four steps: add your month, check and match, run, results. */
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Layout } from '../components/Layout'
import { ErrorCard, Panel, Pill, Readout, Spinner, facilityLabel, monthLabel, num } from '../components/ui'
import { useForecast } from '../hooks/useForecast'
import { ApiError, api, type LoadResult, type UploadPreview, type ValidationReport } from '../lib/api'

type Step = 1 | 2 | 3 | 4

const STEP_LABELS: Record<Step, string> = {
  1: 'Add your month',
  2: 'Check and match',
  3: 'Run models',
  4: 'Results',
}

const REQUIRED_COLUMNS: [string, string][] = [
  ['facility_id', '780'],
  ['product_name', 'Folic Acid 5mg, Tab'],
  ['month', '2023-11'],
  ['received', '0'],
  ['consumption', '120'],
  ['closing_balance', '180'],
]

/** Checks read as a list of findings, not a table — each one is a sentence with
 *  a verdict, and the verdict is a word as well as a colour. */
function Checks({ report }: { report: ValidationReport }) {
  return (
    <div>
      {report.checks.map((check) => (
        <div className="check-row" key={check.id}>
          <span className={`check-mark ${check.level === 'pass' ? 'pass' : check.level === 'warning' ? 'warning' : 'block'}`}>
            {check.level === 'pass' ? '✓' : check.level === 'warning' ? '!' : '✕'}
          </span>
          <span className="check-title">{check.title}</span>
          <span className="check-detail">{check.detail}</span>
        </div>
      ))}
    </div>
  )
}

export default function Upload() {
  const navigate = useNavigate()
  const { runForecast } = useForecast()
  const fileInput = useRef<HTMLInputElement>(null)

  const [step, setStep] = useState<Step>(1)
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<UploadPreview | null>(null)
  const [mapping, setMapping] = useState<Record<string, string>>({})
  const [useCalculated, setUseCalculated] = useState(false)
  const [stored, setStored] = useState<LoadResult | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)

  function fail(err: unknown) {
    if (err instanceof ApiError) {
      const validation = (err.payload as { detail?: { validation?: ValidationReport } })?.detail?.validation
      setError(validation ? `${err.message} — see the checks above.` : err.message)
    } else {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  async function handleFile(selected: File) {
    setBusy('Reading your file…')
    setError(null)
    setFile(selected)
    try {
      const result = await api.uploadFile(selected)
      setPreview(result)
      setMapping(
        Object.fromEntries(
          Object.entries(result.suggested_mapping)
            .filter(([, info]) => info.column)
            .map(([field, info]) => [field, info.column as string]),
        ),
      )
      setStep(2)
    } catch (err) {
      fail(err)
    } finally {
      setBusy(null)
    }
  }

  async function loadDemo() {
    setBusy('Loading the sample facility…')
    setError(null)
    try {
      const result = await api.loadDemo()
      setStored(result)
      setFile(null)
      setPreview(null)
      setStep(3)
    } catch (err) {
      fail(err)
    } finally {
      setBusy(null)
    }
  }

  async function confirmMapping() {
    if (!file) return
    setBusy('Validating…')
    setError(null)
    try {
      const result = await api.confirmUpload(file, mapping, useCalculated)
      setStored(result)
      setStep(3)
    } catch (err) {
      fail(err)
    } finally {
      setBusy(null)
    }
  }

  async function run() {
    setBusy('Building features and running three quantile models…')
    setError(null)
    const result = await runForecast()
    setBusy(null)
    if (result) setStep(4)
    else setError('The forecast could not be generated. Check the month has stock records.')
  }

  const validation = stored?.validation ?? preview?.validation ?? null

  return (
    <Layout
      workspace="warehouse"
      crumb="Warehouse operations"
      title="Upload Data"
      subtitle="Add a month of stock records, then run the forecast."
      isDemo={stored?.is_demo}
      actions={
        <ol className="steps" style={{ listStyle: 'none', margin: 0, padding: 0 }}>
          {([1, 2, 3, 4] as Step[]).map((index) => (
            <li key={index} className={`step${step === index ? ' on' : ''}${step > index ? ' done' : ''}`}>
              <span className="step-n" aria-hidden>{step > index ? '✓' : index}</span>
              <span className="micro">{STEP_LABELS[index]}</span>
              {index < 4 && <span className="step-sep" aria-hidden>›</span>}
            </li>
          ))}
        </ol>
      }
    >
      {error && <ErrorCard title="Upload problem" message={error} />}

      {step === 1 && (
        <div className="split">
          <Panel title="Add your month">
            <div
              className={`dropzone${dragging ? ' over' : ''}`}
              onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault()
                setDragging(false)
                const dropped = e.dataTransfer.files?.[0]
                if (dropped) void handleFile(dropped)
              }}
            >
              <p style={{ fontWeight: 500, color: 'var(--text-900)' }}>Drop a CSV or Excel file here</p>
              <p className="small muted" style={{ marginTop: 4 }}>One row per supply, for one month.</p>
              <div className="row" style={{ justifyContent: 'center', marginTop: 'var(--s-5)' }}>
                <button className="btn btn-primary" onClick={() => fileInput.current?.click()} disabled={busy !== null}>
                  Choose file
                </button>
                <a className="btn" href={api.templateUrl} download>Download template</a>
              </div>
              <input
                ref={fileInput}
                type="file"
                accept=".csv,.xlsx,.xls"
                className="sr-only"
                onChange={(e) => {
                  const selected = e.target.files?.[0]
                  if (selected) void handleFile(selected)
                }}
              />
            </div>
            {busy && <div style={{ marginTop: 'var(--s-4)' }}><Spinner label={busy} /></div>}

            <div className="note" style={{ marginTop: 'var(--s-5)' }}>
              <span className="note-label">No data to hand?</span>
              <div className="note-body small">
                Load one real facility-month from the dataset and run the whole flow. It is badged as
                sample data everywhere it appears.
              </div>
              <div className="row" style={{ marginTop: 'var(--s-3)' }}>
                <button className="btn btn-sm btn-primary" onClick={loadDemo} disabled={busy !== null}>
                  Load demo facility
                </button>
              </div>
            </div>
          </Panel>

          <Panel
            title="What we need from you"
            flush
            note="Six columns, and supplies go by name — no internal codes. Your column names can differ; you confirm a mapping next."
          >
            <div className="table-scroll">
              <table>
                <thead><tr><th>Column</th><th>Example</th></tr></thead>
                <tbody>
                  {REQUIRED_COLUMNS.map(([column, example]) => (
                    <tr key={column}>
                      <td className="mono" style={{ color: 'var(--text-900)' }}>{column}</td>
                      <td className="small muted">{example}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="panel-body" style={{ borderTop: '1px solid var(--line)' }}>
              <span className="note-label" style={{ color: 'var(--gold-700)' }}>Worked out for you</span>
              <ul className="small muted" style={{ margin: '6px 0 0', paddingLeft: 18, lineHeight: 1.8 }}>
                <li>Opening balance — from closing + consumption − received</li>
                <li>Stockout — whether the month ended at zero</li>
                <li>Product code, facility type and district — looked up</li>
              </ul>
              <div style={{ marginTop: 'var(--s-4)' }}><SupplyList /></div>
            </div>
          </Panel>
        </div>
      )}

      {step === 2 && preview && (
        <>
          <Panel
            title="Match your columns"
            aside={<span className="micro muted">{preview.filename} · {num(preview.row_count)} rows</span>}
          >
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 'var(--s-4)' }}>
              {preview.required_fields.map((field) => {
                const suggestion = preview.suggested_mapping[field]
                return (
                  <label key={field}>
                    <span className="field-label" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span className="mono" style={{ textTransform: 'none', letterSpacing: 0 }}>{field}</span>
                      {suggestion?.confidence === 'high' && <Pill tone="ok">matched</Pill>}
                      {suggestion?.confidence === 'low' && <Pill tone="at_risk">check this</Pill>}
                      {suggestion?.confidence === 'none' && <Pill tone="critical">pick one</Pill>}
                    </span>
                    <select
                      className="select"
                      value={mapping[field] ?? ''}
                      onChange={(e) => setMapping({ ...mapping, [field]: e.target.value })}
                    >
                      <option value="">— not mapped —</option>
                      {preview.columns.map((column) => (
                        <option key={column} value={column}>{column}</option>
                      ))}
                    </select>
                  </label>
                )
              })}
            </div>
          </Panel>

          {validation && (
            <Panel title="Checks">
              <Checks report={validation} />
              {validation.checks.some((c) => c.id === 'balance_identity' && c.level === 'warning') && (
                <label className="row" style={{ marginTop: 'var(--s-4)', gap: 'var(--s-2)' }}>
                  <input type="checkbox" checked={useCalculated} onChange={(e) => setUseCalculated(e.target.checked)} />
                  <span className="small">Use the calculated closing balance (opening + received − consumption)</span>
                </label>
              )}
            </Panel>
          )}

          <div className="row">
            <button className="btn btn-primary" onClick={confirmMapping} disabled={busy !== null}>
              {busy ? 'Validating…' : 'Confirm and continue'}
            </button>
            <button className="btn" onClick={() => setStep(1)} disabled={busy !== null}>Back</button>
            {busy && <Spinner label={busy} />}
          </div>
        </>
      )}

      {step === 3 && stored && (
        <div className="split">
          <Panel title="Run the models">
            <p className="small muted">
              Facility {stored.facility_id} · {monthLabel(stored.month)} · {num(stored.stored_rows)} supplies
              {stored.skipped_rows > 0 && ` · ${stored.skipped_rows} row(s) skipped`}
            </p>
            <ol className="small muted" style={{ lineHeight: 2, paddingLeft: 18, margin: 'var(--s-4) 0 0' }}>
              <li>Build 141 leakage-safe features from your history</li>
              <li>Three XGBoost quantile models → P10 / P50 / P90</li>
              <li>Compare the P90 against your stock → shortage or surplus</li>
            </ol>
            <div className="row" style={{ marginTop: 'var(--s-5)' }}>
              <button className="btn btn-primary" onClick={run} disabled={busy !== null}>
                {busy ? 'Running…' : 'Run forecast'}
              </button>
              {busy && <Spinner label={busy} />}
            </div>
          </Panel>

          {stored.validation && (
            <Panel title="Checks"><Checks report={stored.validation} /></Panel>
          )}
        </div>
      )}

      {step === 4 && <Results onNavigate={navigate} />}
    </Layout>
  )
}

/** The 36 tracked supplies, searchable — so a manager can check the exact
 *  spelling Madad expects before uploading, instead of guessing. */
function SupplyList() {
  const [catalogue, setCatalogue] = useState<{ product_id: number; name: string }[]>([])
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)

  useEffect(() => {
    api.products().then((result) => setCatalogue(result.products)).catch(() => setCatalogue([]))
  }, [])

  const shown = catalogue.filter((item) => item.name.toLowerCase().includes(query.toLowerCase()))

  return (
    <div>
      <button className="btn btn-sm" aria-expanded={open} onClick={() => setOpen(!open)}>
        {open ? 'Hide' : 'Show'} the {catalogue.length || 36} supplies Madad tracks
      </button>

      {open && (
        <div className="stack" style={{ marginTop: 'var(--s-3)', gap: 'var(--s-2)' }}>
          <input
            className="input"
            placeholder="Search supplies…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Search the tracked supplies"
          />
          <ul className="small" style={{ margin: 0, paddingLeft: 18, maxHeight: 220, overflowY: 'auto', lineHeight: 1.8 }}>
            {shown.map((item) => <li key={item.product_id}>{item.name}</li>)}
            {shown.length === 0 && <li className="muted">Nothing matches “{query}”.</li>}
          </ul>
          <p className="micro muted">
            Close matches are accepted — “Folic Acid 5mg” finds “Folic Acid 5mg, Tab”.
          </p>
        </div>
      )}
    </div>
  )
}

function Results({ onNavigate }: { onNavigate: (to: string) => void }) {
  const { run } = useForecast()
  if (!run) return null

  return (
    <>
      <section className="statement on-ink">
        <p className="eyebrow">Forecast ready</p>
        <h2 style={{ marginTop: 'var(--s-3)' }}>
          {run.counts.critical > 0
            ? `${run.counts.critical} of ${run.counts.total} supplies fall short`
            : `All ${run.counts.total} supplies are covered`}
        </h2>
        <p className="statement-meta">
          {monthLabel(run.forecast_month)} · {facilityLabel(run.facility)} · solved in {run.generated_in_seconds}s
        </p>
        <div className="row" style={{ marginTop: 'var(--s-6)' }}>
          <button className="btn btn-on-ink" onClick={() => onNavigate('/warehouse/forecasts')}>See forecasts</button>
          <button className="btn btn-ghost-ink" onClick={() => onNavigate('/warehouse/transfers')}>Find donors</button>
          <button className="btn btn-ghost-ink" onClick={() => onNavigate('/warehouse/chat')}>Ask Madad</button>
        </div>
      </section>

      <Readout
        items={[
          { label: 'Short', value: num(run.counts.critical), tone: 'critical' },
          { label: 'At risk', value: num(run.counts.at_risk), tone: 'at_risk' },
          { label: 'Covered', value: num(run.counts.surplus), tone: 'surplus' },
          { label: 'Supplies tracked', value: num(run.counts.total) },
        ]}
      />
    </>
  )
}
