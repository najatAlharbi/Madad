import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Navigate, Route, BrowserRouter as Router, Routes } from 'react-router-dom'
import { AuthorityHome, AuthorityShortages, AuthorityTransfers } from './pages/Authority'
import Chat from './pages/Chat'
import Forecasts from './pages/Forecasts'
import Landing from './pages/Landing'
import Transfers from './pages/Transfers'
import Upload from './pages/Upload'
import WarehouseHome from './pages/WarehouseHome'
import WarehouseShell from './pages/WarehouseShell'
import './styles/tokens.css'
import './styles/app.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Router>
      <Routes>
        <Route path="/" element={<Landing />} />

        {/* Warehouse screens share one forecast state and one expiry screen. */}
        <Route path="/warehouse" element={<WarehouseShell />}>
          <Route index element={<WarehouseHome />} />
          <Route path="upload" element={<Upload />} />
          <Route path="forecasts" element={<Forecasts />} />
          <Route path="transfers" element={<Transfers />} />
          <Route path="chat" element={<Chat />} />
        </Route>

        {/* Authority is read-only and needs no session. */}
        <Route path="/authority" element={<AuthorityHome />} />
        <Route path="/authority/shortages" element={<AuthorityShortages />} />
        <Route path="/authority/transfers" element={<AuthorityTransfers />} />

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Router>
  </StrictMode>,
)
