/** The forecast chart from design/screens.md.
 *
 * 13 months: solid line = actual consumption, dashed green = forecast (P50),
 * sage area = the P10–P90 range opening from the last actual month, dashed
 * gold reference line = stock on hand. The final month is shaded and
 * labelled FORECAST.
 *
 * Recharts needs the band as [low, high] pairs, and nulls break a line —
 * which is what we want: `actual` stops at the last real month and
 * `forecast` starts there, so the two meet without overlapping.
 */
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { HistoryPoint } from '../lib/api'
import { num, shortMonth } from './ui'

interface Props {
  history: HistoryPoint[]
  stock: number
  productName: string
}

export function ForecastChart({ history, stock, productName }: Props) {
  const data = history.map((point, index) => ({
    month: point.month,
    label: shortMonth(point.month, index === 0 || point.month.endsWith('-01')),
    actual: point.actual,
    forecast: point.forecast,
    range: point.range ?? undefined,
  }))

  const forecastMonth = data[data.length - 1]?.month

  const values = history.flatMap((p) => [p.actual, p.forecast, p.range?.[0], p.range?.[1]]).filter((v): v is number => v != null)
  const upper = Math.max(stock, ...values, 1)

  return (
    <figure style={{ margin: 0 }}>
      {/* Chart alternative text, required by the accessibility rules. */}
      <figcaption className="sr-only">
        Forecast for {productName}. Monthly consumption for the past year, then next month's
        forecast of {num(history[history.length - 1]?.forecast)} units with a range from{' '}
        {num(history[history.length - 1]?.range?.[0])} to {num(history[history.length - 1]?.range?.[1])} units.
        Stock on hand is {num(stock)} units.
      </figcaption>

      <div style={{ width: '100%', height: 280 }}>
        <ResponsiveContainer>
          <ComposedChart data={data} margin={{ top: 10, right: 12, bottom: 0, left: -12 }}>
            <CartesianGrid stroke="var(--line)" vertical={false} />
            <XAxis
              dataKey="label"
              tick={{ fontSize: 11, fill: 'var(--text-500)', fontFamily: 'var(--font-mono)' }}
              axisLine={{ stroke: 'var(--line-2)' }}
              tickLine={false}
              interval="preserveStartEnd"
            />
            <YAxis
              tick={{ fontSize: 11, fill: 'var(--text-500)', fontFamily: 'var(--font-mono)' }}
              axisLine={false}
              tickLine={false}
              domain={[0, Math.ceil(upper * 1.1)]}
              width={56}
            />
            <Tooltip
              contentStyle={{
                borderRadius: 'var(--r-panel)',
                border: '1px solid var(--line-2)',
                boxShadow: 'var(--shadow-pop)',
                fontSize: 12,
                fontFamily: 'var(--font-mono)',
                fontVariantNumeric: 'tabular-nums',
              }}
              labelStyle={{ fontFamily: 'var(--font-ui)', color: 'var(--text-900)', fontWeight: 500 }}
              formatter={(value, name) => {
                if (Array.isArray(value)) return [`${num(value[0])} – ${num(value[1])} units`, name]
                return [`${num(value as number)} units`, name]
              }}
            />
            <Legend wrapperStyle={{ fontSize: 11, paddingTop: 10 }} iconType="plainline" />

            {/* Shade the forecast month so the projection reads as distinct. */}
            {forecastMonth && (
              <ReferenceArea
                x1={data[data.length - 2]?.label}
                x2={data[data.length - 1]?.label}
                fill="var(--paper-2)"
                fillOpacity={0.8}
                label={{ value: 'FORECAST', position: 'insideTop', fontSize: 9, fill: 'var(--gold-700)', letterSpacing: 1.6 }}
              />
            )}

            <Area
              dataKey="range"
              name="Forecast range (P10–P90)"
              stroke="none"
              fill="var(--green-200)"
              fillOpacity={0.85}
              connectNulls
              isAnimationActive={false}
            />
            <Line
              dataKey="actual"
              name="Actual consumption"
              stroke="var(--ink-800)"
              strokeWidth={2}
              dot={{ r: 2.5 }}
              activeDot={{ r: 4 }}
              isAnimationActive={false}
            />
            <Line
              dataKey="forecast"
              name="Forecasted consumption (P50)"
              stroke="var(--green-700)"
              strokeWidth={2.5}
              strokeDasharray="7 5"
              dot={{ r: 3 }}
              connectNulls
              isAnimationActive={false}
            />
            <ReferenceLine
              y={stock}
              stroke="var(--gold-600)"
              strokeDasharray="5 4"
              strokeWidth={2}
              label={{ value: 'Stock on hand', position: 'insideBottomRight', fontSize: 10, fill: 'var(--gold-700)' }}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </figure>
  )
}
