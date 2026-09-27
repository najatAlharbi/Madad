/** Landing: a brief loading state, then the workspace chooser.
 *
 *  Not a marketing hero. Two columns: the choice on paper, the network's real
 *  figures on ink. The two workspaces are rows on a ruled list, because that is
 *  what they are — a choice between two, not two products to compare.
 */
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import logo from '../assets/logo.png'
import { api, type HealthResponse, type Role } from '../lib/api'

const LOADING_MS = 1400

const WORKSPACES: { role: Role; index: string; name: string; desc: string; cta: string }[] = [
  {
    role: 'warehouse',
    index: '01',
    name: 'Hospital Warehouse Manager',
    desc: 'Upload your monthly stock, see what next month will need, and find the nearest warehouse that can send what is missing.',
    cta: 'Can upload data',
  },
  {
    role: 'authority',
    index: '02',
    name: 'Regulatory Authority',
    desc: 'The whole network at a glance: where shortages are, what moving stock can fix, and what has to be bought.',
    cta: 'View only',
  },
]

export default function Landing() {
  const navigate = useNavigate()
  const [booting, setBooting] = useState(true)
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [busy, setBusy] = useState<Role | null>(null)
  const [openError, setOpenError] = useState<string | null>(null)

  useEffect(() => {
    // Use the pause to confirm the backend is actually up, so a visitor
    // learns about a dead API here rather than on a blank page later.
    api.health().then(setHealth).catch(() => setHealth(null))
    const timer = setTimeout(() => setBooting(false), LOADING_MS)
    return () => clearTimeout(timer)
  }, [])

  async function choose(role: Role) {
    setOpenError(null)
    setBusy(role)
    try {
      await api.setSession(role)
      navigate(role === 'warehouse' ? '/warehouse' : '/authority')
    } catch (error) {
      setOpenError(error instanceof Error ? error.message : 'Unable to connect. Start the backend and retry.')
    } finally {
      setBusy(null)
    }
  }

  if (booting) {
    return (
      <div className="boot on-ink">
        <div className="boot-inner">
          <img src={logo} alt="" style={{ width: 44, height: 50, objectFit: 'contain' }} />
          <div style={{ textAlign: 'center' }}>
            <div className="wordmark" style={{ color: 'var(--on-dark)' }}>MADAD</div>
            <div className="wordmark-sub">Medical Logistics</div>
          </div>
          <div className="boot-track" role="progressbar" aria-label="Starting Madad"><span /></div>
          <button className="btn btn-sm btn-ghost-ink" onClick={() => setBooting(false)}>Skip</button>
        </div>
      </div>
    )
  }

  const coverage = health?.last_evaluation_metrics?.coverage_p10_p90

  return (
    <div className="landing rise">
      <div className="landing-main">
        <div>
          <div className="row" style={{ gap: 'var(--s-3)' }}>
            <img src={logo} alt="" style={{ width: 40, height: 46, objectFit: 'contain' }} />
            <span>
              <span className="wordmark" style={{ color: 'var(--text-900)' }}>MADAD</span>
              <span className="wordmark-sub" style={{ color: 'var(--text-500)' }}>Medical Logistics</span>
            </span>
          </div>

          <h1 className="landing-title" style={{ marginTop: 'var(--s-8)' }}>
            Every connection makes a difference.
          </h1>
          <p className="landing-lede" style={{ marginTop: 'var(--s-4)' }}>
            Madad forecasts next month's medicine needs for every hospital warehouse, then shows
            where the missing stock already sits — and how far away it is.
          </p>
        </div>

        {!health && (
          <div className="alert stack" role="alert">
            <h2>Backend not reachable</h2>
            <p className="small">
              Start it with <code className="mono">uvicorn app.main:app --reload --port 8000</code> from{' '}
              <code className="mono">backend/</code>, then reload this page.
            </p>
          </div>
        )}

        <div>
          <p className="field-label">Choose your workspace</p>
          {openError && <p className="alert" role="alert">{openError}</p>}
          {WORKSPACES.map((workspace) => (
            <button
              key={workspace.role}
              className="choice"
              onClick={() => choose(workspace.role)}
              disabled={busy !== null}
            >
              <span className="choice-index">{workspace.index}</span>
              <span>
                <span className="choice-name">{workspace.name}</span>
                <span className="choice-desc">{workspace.desc}</span>
                <span className="micro muted" style={{ display: 'block', marginTop: 'var(--s-3)' }}>
                  {workspace.cta}
                </span>
              </span>
              <span className="choice-go">
                {busy === workspace.role ? 'Opening…' : 'Open →'}
              </span>
            </button>
          ))}
          <a className="choice" href="/pharmacist/index.html" style={{textDecoration: 'none'}}><span className="choice-index">03</span><span><span className="choice-name">Hospital Pharmacist</span><span className="choice-desc">Search medicines by name, upload a pill photo or use your camera. Review candidates before recording dispensing.</span></span><span className="choice-go">Open →</span></a>
        </div>
      </div>

      <div className="landing-aside on-ink">
        <div>
          <p className="eyebrow" style={{ color: 'var(--gold-400)' }}>What it watches</p>
          <h2
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: 'var(--t-title)',
              fontWeight: 400,
              color: 'var(--on-dark)',
              marginTop: 'var(--s-2)',
              maxWidth: '18ch',
            }}
          >
            One network, measured monthly.
          </h2>
        </div>

        <div className="stack" style={{ gap: 'var(--s-6)' }}>
          <div className="figure-row">
            <span className="figure-value">1,091</span>
            <span className="figure-label">hospital warehouses</span>
          </div>
          <div className="figure-row">
            <span className="figure-value">36</span>
            <span className="figure-label">essential supplies tracked</span>
          </div>
          <div className="figure-row">
            <span className="figure-value">{coverage != null ? `${(coverage * 100).toFixed(1)}%` : '—'}</span>
            <span className="figure-label">actuals inside P10–P90, unseen months</span>
          </div>
        </div>

        <p className="micro" style={{ color: 'var(--on-dark-faint)', maxWidth: '38ch', lineHeight: 1.6 }}>
          Proof of concept on Sierra Leone essential-medicines data (Dryad).
        </p>
      </div>
    </div>
  )
}
