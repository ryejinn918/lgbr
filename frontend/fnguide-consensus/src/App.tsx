import { Navigate, NavLink, Route, Routes, useSearchParams } from 'react-router-dom'
import { ComparePage } from './pages/ComparePage'
import { FramesPage } from './pages/FramesPage'
import { OpsPage } from './pages/OpsPage'
import './App.css'

function RedirectOps() {
  const [params] = useSearchParams()
  const theme = params.get('theme')
  return <Navigate to={theme ? `/ops?theme=${theme}` : '/ops'} replace />
}

function App() {
  return (
    <div className="monitor">
      <header className="app-shell">
        <p className="brand">fnguide-consensus</p>
        <nav className="app-nav" aria-label="주요 메뉴">
          <NavLink to="/" end>
            비교
          </NavLink>
          <NavLink to="/frames">프레임</NavLink>
          <NavLink to="/ops">운영</NavLink>
        </nav>
      </header>
      <Routes>
        <Route path="/" element={<ComparePage />} />
        <Route path="/frames" element={<FramesPage />} />
        <Route path="/frames/:runId" element={<Navigate to="/frames" replace />} />
        <Route path="/ops" element={<OpsPage />} />
        <Route path="/inputs" element={<RedirectOps />} />
        <Route path="/run" element={<RedirectOps />} />
        <Route path="/monitor" element={<RedirectOps />} />
      </Routes>
    </div>
  )
}

export default App
