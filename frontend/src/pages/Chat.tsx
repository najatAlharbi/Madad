/** Ask Madad — grounded assistant. Every answer shows what it looked at. */
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Layout } from '../components/Layout'
import { ErrorCard, Panel, Pill, Spinner, num } from '../components/ui'
import { useForecast } from '../hooks/useForecast'
import { ApiError, SessionExpiredError, api, type ChatHistory, type ChatTurn } from '../lib/api'

const CONTEXT_LABELS: Record<string, string> = {
  forecast_run: 'your forecast',
  'forecast_run.filtered': 'your forecast (largest gaps)',
  transfer_plan: 'transfer suggestions',
  network_summary: 'network summary',
}

export default function Chat() {
  const { run } = useForecast()
  const [meta, setMeta] = useState<ChatHistory | null>(null)
  const [turns, setTurns] = useState<ChatTurn[]>([])
  const [lastKeys, setLastKeys] = useState<string[]>([])
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    api
      .chatHistory()
      .then((result) => { setMeta(result); setTurns(result.history) })
      .catch((err) => setError(err instanceof SessionExpiredError ? 'Your session expired — please generate the forecast again.' : String(err)))
  }, [])

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [turns, busy])

  async function send(message: string) {
    const text = message.trim()
    if (!text || busy) return
    setDraft('')
    setError(null)
    setTurns((current) => [...current, { role: 'user', content: text, at: Date.now() / 1000 }])
    setBusy(true)
    try {
      const result = await api.chat(text)
      setTurns((current) => [...current, { role: 'assistant', content: result.answer, at: Date.now() / 1000 }])
      setLastKeys(result.used_context_keys)
    } catch (err) {
      if (err instanceof SessionExpiredError) setError('Your session expired — please generate the forecast again.')
      else if (err instanceof ApiError && err.code === 'llm_not_configured') setError(err.message)
      else setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const notConfigured = meta && !meta.configured

  return (
    <Layout
      workspace="warehouse"
      crumb="Warehouse operations"
      title="Ask Madad"
      subtitle="Answers come only from your forecast and the transfer plan."
      isDemo={run?.is_demo}
    >
      {notConfigured && (
        <ErrorCard
          title="Assistant not configured"
          message="No LLM API key is set, so the assistant is switched off. Add GROQ_API_KEY to backend/.env and restart the backend. Madad will not invent an answer without it."
        />
      )}

      <div className="split">
        <Panel
          title="Conversation"
          aside={meta?.model && <span className="micro mono muted">{meta.model}</span>}
          note={
            lastKeys.length > 0 ? (
              <span className="row" style={{ gap: 6 }}>
                <span>Based on:</span>
                {lastKeys.map((key) => <Pill key={key} tone="neutral">{CONTEXT_LABELS[key] ?? key}</Pill>)}
              </span>
            ) : undefined
          }
        >
          <div className="stack" style={{ minHeight: 420 }}>
            <div className="thread scroll-y" style={{ flexGrow: 1, maxHeight: 400, paddingRight: 4 }}>
              {turns.length === 0 && !busy && (
                <p className="small muted">
                  {run
                    ? `Ask about ${run.counts.total} supplies forecast for ${run.forecast_month}.`
                    : 'Run a forecast first, then ask about it.'}
                </p>
              )}
              {turns.map((turn, index) => (
                <div
                  key={`${turn.at}-${index}`}
                  className={`turn ${turn.role === 'user' ? 'turn-user' : 'turn-bot'}`}
                  lang={turn.role === 'assistant' && /[؀-ۿ]/.test(turn.content) ? 'ar' : undefined}
                  dir={turn.role === 'assistant' && /[؀-ۿ]/.test(turn.content) ? 'rtl' : undefined}
                >
                  {turn.content}
                </div>
              ))}
              {busy && <div className="turn turn-bot"><Spinner label="Thinking…" /></div>}
              <div ref={endRef} />
            </div>

            {error && <p className="small" style={{ color: 'var(--critical-fg)' }}>{error}</p>}

            <form
              className="row"
              style={{ gap: 'var(--s-2)', flexWrap: 'nowrap' }}
              onSubmit={(e) => { e.preventDefault(); void send(draft) }}
            >
              <input
                className="input"
                placeholder={notConfigured ? 'Assistant unavailable' : 'Ask about a supply, a shortage or a transfer…'}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                disabled={busy || !!notConfigured}
                aria-label="Your question"
              />
              <button className="btn btn-primary" type="submit" disabled={busy || !draft.trim() || !!notConfigured}>
                Send
              </button>
            </form>
          </div>
        </Panel>

        <div className="stack" style={{ gap: 'var(--s-5)' }}>
          <Panel title="Try asking">
            {(meta?.suggested_questions ?? []).map((question) => (
              <button
                key={question}
                className="suggest"
                onClick={() => void send(question)}
                disabled={busy || !!notConfigured}
              >
                {question}
              </button>
            ))}
          </Panel>

          <Panel title="What it can look up">
            <ul className="small muted" style={{ margin: 0, paddingLeft: 18, lineHeight: 1.9 }}>
              <li>Your forecast {meta?.can_look_up.forecast_run ? '✓' : '— run one first'}</li>
              <li>Transfer suggestions {meta?.can_look_up.transfer_plan ? '✓' : '— open Get & Share Stock'}</li>
              <li>Network summary ✓</li>
            </ul>

            <h2 style={{ marginTop: 'var(--s-5)' }}>Guardrails</h2>
            <ul className="small muted" style={{ margin: '6px 0 0', paddingLeft: 18, lineHeight: 1.9 }}>
              <li>Answers only from the numbers above</li>
              <li>Never invents a figure</li>
              <li>Says what is missing when it cannot answer</li>
              <li>Replies in English or Arabic</li>
              <li>No clinical or prescribing advice</li>
            </ul>
          </Panel>

          {run && (
            <Panel title="This month">
              <p className="small muted">
                <span className="mono">{num(run.counts.critical)}</span> critical ·{' '}
                <span className="mono">{num(run.counts.at_risk)}</span> at risk ·{' '}
                <span className="mono">{num(run.counts.surplus)}</span> with spare stock.{' '}
                <Link to="/warehouse/forecasts">See the detail</Link>
              </p>
            </Panel>
          )}
        </div>
      </div>
    </Layout>
  )
}
