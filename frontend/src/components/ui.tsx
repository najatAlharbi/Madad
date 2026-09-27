/** Shared presentational pieces.
 *
 *  Two rules hold across all of them:
 *   - Status colour is never used alone — every tag carries its status word.
 *   - A quantity is a measurement: monospaced, tabular, right-aligned in tables.
 */
import type { ReactNode } from 'react'
import type { Severity } from '../lib/api'

const SEVERITY_LABEL: Record<Severity, string> = {
  critical: 'Critical',
  at_risk: 'At risk',
  surplus: 'Surplus',
}

export function StatusPill({ severity }: { severity: Severity }) {
  return <span className={`tag tag-${severity}`}>{SEVERITY_LABEL[severity]}</span>
}

export function Pill({
  tone = 'neutral',
  children,
}: {
  tone?: 'critical' | 'at_risk' | 'surplus' | 'ok' | 'neutral'
  children: ReactNode
}) {
  return <span className={`tag tag-plain tag-${tone}`}>{children}</span>
}

export function DemoBadge() {
  return (
    <span className="sample-tag" title="These numbers come from the bundled sample facility">
      Sample data
    </span>
  )
}

/** A panel: one hairline surface, optional head and footnote. Deliberately not
 *  a shadowed card — pages are composed from rules, not floating tiles. */
export function Panel({
  title,
  aside,
  note,
  flush,
  children,
  labelledBy,
}: {
  title?: ReactNode
  aside?: ReactNode
  note?: ReactNode
  flush?: boolean
  children?: ReactNode
  labelledBy?: string
}) {
  return (
    <section className="panel" aria-labelledby={labelledBy}>
      {(title || aside) && (
        <div className="panel-head">
          {typeof title === 'string' ? <h2>{title}</h2> : title}
          {aside}
        </div>
      )}
      {children != null && <div className={flush ? 'panel-body-flush' : 'panel-body'}>{children}</div>}
      {note && <div className="panel-note">{note}</div>}
    </section>
  )
}

/** The measurement strip. Four single-digit counts do not each deserve their own
 *  box; read as one instrument they compare at a glance. */
export function Readout({
  items,
}: {
  items: { label: string; value: ReactNode; unit?: string; tone?: Severity }[]
}) {
  return (
    <div className="readout">
      {items.map((item) => (
        <div className="readout-cell" key={item.label}>
          <div className="readout-label">{item.label}</div>
          <div className={`readout-value${item.tone ? ` is-${item.tone}` : ''}`}>
            {item.value}
            {item.unit && <span className="readout-unit">{item.unit}</span>}
          </div>
        </div>
      ))}
    </div>
  )
}

/** Coverage meter — the signature mark.
 *
 *  One glance answers the product's whole question: does the stock I hold reach
 *  the demand we expect? The pale band is the P10–P90 forecast range, the notch
 *  is P50 (expected demand), and the solid fill is stock on hand. Everything is
 *  scaled to P90 × 1.15 so a comfortable surplus visibly overshoots the band
 *  instead of pinning at the end.
 */
export function CoverageMeter({
  stock,
  p10,
  p50,
  p90,
  tone,
}: {
  stock: number
  p10: number
  p50: number
  p90: number
  tone?: Severity
}) {
  const scale = Math.max(p90 * 1.15, stock, 1)
  const pct = (value: number) => `${Math.max(0, Math.min(100, (value / scale) * 100))}%`
  const covered = p90 > 0 ? Math.round((Math.min(stock / p90, 1)) * 100) : 100

  return (
    <div>
      <div
        className="meter"
        role="img"
        aria-label={`${num(stock)} units in stock against a forecast of ${num(p50)} (range ${num(p10)} to ${num(p90)}) — ${covered}% of the high forecast covered`}
      >
        <span className="meter-band" style={{ left: pct(p10), right: `calc(100% - ${pct(p90)})` }} />
        <span className={`meter-fill${tone ? ` is-${tone}` : ''}`} style={{ width: pct(stock) }} />
        <span className="meter-notch" style={{ left: pct(p50) }} />
      </div>
      <div className="meter-scale">
        <span>{num(stock)} in stock</span>
        <span>{covered}% of P90</span>
      </div>
    </div>
  )
}

/** Plain proportion bar, for coverage percentages that have no forecast band. */
export function CoverageBar({ pct, tone }: { pct: number; tone?: Severity }) {
  const clamped = Math.max(0, Math.min(100, pct))
  return (
    <div className="meter" role="img" aria-label={`${clamped.toFixed(0)}% covered`}>
      <span className={`meter-fill${tone ? ` is-${tone}` : ''}`} style={{ width: `${clamped}%` }} />
    </div>
  )
}

/** Percentage → the severity a coverage figure implies. */
export function coverageTone(pct: number | null | undefined): Severity {
  const value = pct ?? 0
  if (value >= 99) return 'surplus'
  if (value > 0) return 'at_risk'
  return 'critical'
}

export function Spinner({ label }: { label?: string }) {
  return (
    <span className="row" style={{ gap: 'var(--s-2)' }}>
      <span className="spinner" aria-hidden />
      {label && <span className="small muted">{label}</span>}
    </span>
  )
}

/** Loading placeholder that keeps the page's shape instead of collapsing it. */
export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="panel" role="status" aria-live="polite">
      <div className="panel-body stack">
        <Spinner label={label} />
        <div className="skeleton" style={{ width: '62%' }} />
        <div className="skeleton" style={{ width: '88%' }} />
        <div className="skeleton" style={{ width: '44%' }} />
      </div>
    </div>
  )
}

export function EmptyState({ title, body, action }: { title: string; body?: ReactNode; action?: ReactNode }) {
  return (
    <div className="panel" role="status">
      <div className="panel-body stack">
        <h2>{title}</h2>
        {body && <p className="small muted">{body}</p>}
        {action && <div className="row">{action}</div>}
      </div>
    </div>
  )
}

export function ErrorCard({ title, message, action }: { title: string; message: string; action?: ReactNode }) {
  return (
    <div className="alert stack" role="alert">
      <h2>{title}</h2>
      <p className="small">{message}</p>
      {action && <div className="row">{action}</div>}
    </div>
  )
}

/** Assistant commentary. Marked as generated, never styled to look like a fact. */
export function AiNote({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div className="note">
      <span className="note-label">Madad assistant</span>
      <div className="note-body small">{children}</div>
      {action && <div className="row" style={{ marginTop: 'var(--s-3)' }}>{action}</div>}
    </div>
  )
}

/** Integers with thousands separators; one decimal only when it matters. */
export function num(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—'
  return Number.isInteger(value) ? value.toLocaleString() : value.toLocaleString(undefined, { maximumFractionDigits: 1 })
}

/** The dataset never names individual facilities — only a numeric id, a
 *  type (CHC/CHP/MCHP/Hospital) and a district. Rather than show the bare
 *  number as the primary label, show what's actually known: real type and
 *  district, id kept as a parenthetical for anyone who needs the exact
 *  record. Never invents a name. */
export function facilityLabel(facility: {
  id: number
  facility_type?: string | null
  district?: string | null
} | null | undefined): string {
  if (!facility) return '—'
  const parts = [facility.facility_type, facility.district].filter(Boolean)
  return parts.length ? `${parts.join(' · ')} (#${facility.id})` : `Facility #${facility.id}`
}

/** "2023-04" -> "April 2023" */
export function monthLabel(month: string | null | undefined): string {
  if (!month) return '—'
  const [year, mon] = month.split('-').map(Number)
  if (!year || !mon) return month
  return new Date(year, mon - 1, 1).toLocaleDateString(undefined, { month: 'long', year: 'numeric' })
}

/** "2023-04" -> "Apr" / "Apr ’23" for chart ticks */
export function shortMonth(month: string, withYear = false): string {
  const [year, mon] = month.split('-').map(Number)
  if (!year || !mon) return month
  const label = new Date(year, mon - 1, 1).toLocaleDateString(undefined, { month: 'short' })
  return withYear ? `${label} ’${String(year).slice(2)}` : label
}
