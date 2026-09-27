/** Workspace shell: a dark rail for structure, a paper working surface for
 *  content. The rail carries identity and navigation so every page below it
 *  can start straight into the work.
 */
import type { ReactNode } from 'react'
import { Link, NavLink, useNavigate } from 'react-router-dom'
import logo from '../assets/logo.png'
import { api } from '../lib/api'
import { DemoBadge } from './ui'

const WAREHOUSE_NAV = [
  { to: '/warehouse', label: 'My Warehouse' },
  { to: '/warehouse/forecasts', label: 'Forecasted Needs' },
  { to: '/warehouse/transfers', label: 'Get & Share Stock' },
  { to: '/warehouse/upload', label: 'Upload Data' },
  { to: '/warehouse/chat', label: 'Ask Madad' },
]

const AUTHORITY_NAV = [
  { to: '/authority', label: 'Network Overview' },
  { to: '/authority/shortages', label: 'Shortages & Procurement' },
  { to: '/authority/transfers', label: 'Transfer Network' },
]

interface Props {
  workspace: 'warehouse' | 'authority'
  crumb: string
  title: string
  subtitle?: ReactNode
  actions?: ReactNode
  isDemo?: boolean
  facilityLabel?: string
  children: ReactNode
}

export function Layout({ workspace, crumb, title, subtitle, actions, isDemo, facilityLabel, children }: Props) {
  const navigate = useNavigate()
  const items = workspace === 'warehouse' ? WAREHOUSE_NAV : AUTHORITY_NAV
  const isWarehouse = workspace === 'warehouse'

  async function switchWorkspace() {
    await api.endSession().catch(() => undefined)
    navigate('/')
  }

  return (
    <div className="shell">
      <aside className="rail on-ink">
        <Link className="brand" to="/" aria-label="Madad home">
          <img src={logo} alt="" />
          <span>
            <span className="wordmark">MADAD</span>
            <span className="wordmark-sub">Medical Logistics</span>
          </span>
        </Link>

        <div className="rail-label">{isWarehouse ? 'Warehouse' : 'Authority'}</div>

        <nav aria-label={isWarehouse ? 'Warehouse' : 'Authority'}>
          {items.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/warehouse' || item.to === '/authority'}
              className={({ isActive }) => (isActive ? 'nav on' : 'nav')}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="rail-foot">
          {facilityLabel && (
            <div>
              <div className="rail-label" style={{ padding: 0 }}>Facility</div>
              <div className="rail-facility" style={{ marginTop: 4 }}>{facilityLabel}</div>
            </div>
          )}
          <p className="rail-note">
            Sessions are held in memory for 60 minutes. Nothing is written to a database.
          </p>
          <button className="btn btn-sm btn-ghost-ink" onClick={switchWorkspace}>Switch workspace</button>
        </div>
      </aside>

      <main className="work">
        <header className="page-head">
          <div style={{ minWidth: 0 }}>
            <p className="eyebrow">{crumb}</p>
            <h1 style={{ marginTop: 'var(--s-2)' }}>{title}</h1>
            {subtitle && <p className="page-sub">{subtitle}</p>}
          </div>
          <div className="identity">
            {isDemo && <DemoBadge />}
            {actions}
            <span className="portal-tag">{isWarehouse ? 'Warehouse' : 'Authority'} portal</span>
            <span className="avatar" role="img" aria-label={isWarehouse ? 'Warehouse manager' : 'Authority analyst'}>
              {isWarehouse ? 'WM' : 'RA'}
            </span>
          </div>
        </header>

        <div className="page-body">
          {children}

          <footer className="page-foot">
            Proof of concept on Sierra Leone essential-medicines data (Dryad). Forecasts are decision
            support, not a prescribing or procurement authority.
          </footer>
        </div>
      </main>
    </div>
  )
}
