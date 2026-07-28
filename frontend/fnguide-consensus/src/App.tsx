import {
  Navigate,
  NavLink,
  Outlet,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useParams,
  useSearchParams,
} from 'react-router-dom'
import { CompareStoreProvider } from './compare/CompareStore'
import { APP_BRAND, NAV } from './lib/labels'
import {
  DEFAULT_THEME,
  THEMES,
  parseTab,
  parseTheme,
  themePath,
  type AppTab,
} from './lib/theme'
import { ComparePage } from './pages/ComparePage'
import { FramesPage } from './pages/FramesPage'
import { OpsPage } from './pages/OpsPage'
import { SelectPage } from './pages/SelectPage'
import { THEME_LABEL, type ConsensusTheme } from './types'
import './App.css'

function LegacyThemeRedirect({ tab }: { tab: AppTab }) {
  const [params] = useSearchParams()
  const theme = parseTheme(params.get('theme'))
  return <Navigate to={themePath(theme, tab)} replace />
}

function LegacyFramesRunRedirect() {
  const { runId } = useParams()
  const [params] = useSearchParams()
  const theme = parseTheme(params.get('theme'))
  const base = themePath(theme, 'frames')
  const to = runId ? `${base}?run=${encodeURIComponent(runId)}` : base
  return <Navigate to={to} replace />
}

function AppShell() {
  const { theme: raw } = useParams()
  const theme = parseTheme(raw)
  const location = useLocation()
  const navigate = useNavigate()
  const tab = parseTab(location.pathname)

  if (raw && raw !== theme) {
    return <Navigate to={themePath(theme, tab)} replace />
  }

  function switchTheme(next: ConsensusTheme) {
    navigate(themePath(next, tab), { replace: true })
  }

  return (
    <div className="monitor">
      <header className="app-shell">
        <p className="brand">{APP_BRAND}</p>
        <div className="chip-row app-theme-chips" role="group" aria-label="섹터">
          {THEMES.map((t) => (
            <button
              key={t}
              type="button"
              className={`chip ${theme === t ? 'active' : ''}`}
              onClick={() => switchTheme(t)}
            >
              {THEME_LABEL[t]}
            </button>
          ))}
        </div>
        <nav className="app-nav" aria-label="주요 메뉴">
          <NavLink to={themePath(theme, 'compare')}>{NAV.compare}</NavLink>
          <NavLink to={themePath(theme, 'frames')}>{NAV.frames}</NavLink>
          <NavLink to={themePath(theme, 'select')}>{NAV.select}</NavLink>
          <NavLink to={themePath(theme, 'ops')}>{NAV.ops}</NavLink>
        </nav>
      </header>
      <Outlet />
    </div>
  )
}

function App() {
  return (
    <CompareStoreProvider>
      <Routes>
        <Route
          path="/"
          element={<Navigate to={themePath(DEFAULT_THEME, 'ops')} replace />}
        />
        <Route path="/compare" element={<LegacyThemeRedirect tab="compare" />} />
        <Route path="/frames" element={<LegacyThemeRedirect tab="frames" />} />
        <Route path="/frames/:runId" element={<LegacyFramesRunRedirect />} />
        <Route path="/ops" element={<LegacyThemeRedirect tab="ops" />} />
        <Route path="/select" element={<LegacyThemeRedirect tab="select" />} />
        <Route path="/inputs" element={<LegacyThemeRedirect tab="select" />} />
        <Route path="/run" element={<LegacyThemeRedirect tab="ops" />} />
        <Route path="/monitor" element={<LegacyThemeRedirect tab="ops" />} />
        <Route path="/:theme" element={<AppShell />}>
          <Route index element={<Navigate to="ops" replace />} />
          <Route path="ops" element={<OpsPage />} />
          <Route path="select" element={<SelectPage />} />
          <Route path="frames" element={<FramesPage />} />
          <Route path="compare" element={<ComparePage />} />
          <Route path="*" element={<Navigate to="ops" replace />} />
        </Route>
      </Routes>
    </CompareStoreProvider>
  )
}

export default App
