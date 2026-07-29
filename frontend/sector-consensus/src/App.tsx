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
import { AppStatus } from './components/AppStatus'
import { ConsensusStatusProvider } from './hooks/ConsensusStatusContext'
import { APP_BRAND, NAV } from './lib/labels'
import {
  DEFAULT_THEME,
  THEMES,
  parseTab,
  parseTheme,
  themePath,
  type AppTab,
} from './lib/theme'
import { AxesPage } from './pages/AxesPage'
import { FramesPage } from './pages/FramesPage'
import { THEME_LABEL, type ConsensusTheme } from './types'
import './App.css'

function LegacyThemeRedirect({ tab }: { tab: AppTab }) {
  const [params] = useSearchParams()
  const theme = parseTheme(params.get('theme'))
  const run = params.get('run')
  const base = themePath(theme, tab)
  const to = run ? `${base}?run=${encodeURIComponent(run)}` : base
  return <Navigate to={to} replace />
}

function LegacyFramesRunRedirect() {
  const { runId } = useParams()
  const [params] = useSearchParams()
  const theme = parseTheme(params.get('theme'))
  const base = themePath(theme, 'frames')
  const to = runId ? `${base}?run=${encodeURIComponent(runId)}` : base
  return <Navigate to={to} replace />
}

/** Preserve ?run= when folding former select routes into axes. */
function RedirectToAxesKeepSearch() {
  const [params] = useSearchParams()
  const run = params.get('run')
  const to = run ? `../axes?run=${encodeURIComponent(run)}` : '../axes'
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
    <ConsensusStatusProvider theme={theme}>
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
            <NavLink to={themePath(theme, 'axes')}>{NAV.axes}</NavLink>
            <NavLink to={themePath(theme, 'frames')}>{NAV.frames}</NavLink>
          </nav>
        </header>
        <AppStatus />
        <Outlet />
      </div>
    </ConsensusStatusProvider>
  )
}

function App() {
  return (
    <Routes>
      <Route
        path="/"
        element={<Navigate to={themePath(DEFAULT_THEME, 'axes')} replace />}
      />
      <Route path="/compare" element={<LegacyThemeRedirect tab="axes" />} />
      <Route path="/frames" element={<LegacyThemeRedirect tab="frames" />} />
      <Route path="/frames/:runId" element={<LegacyFramesRunRedirect />} />
      <Route path="/ops" element={<LegacyThemeRedirect tab="axes" />} />
      <Route path="/axes" element={<LegacyThemeRedirect tab="axes" />} />
      <Route path="/select" element={<LegacyThemeRedirect tab="axes" />} />
      <Route path="/inputs" element={<LegacyThemeRedirect tab="axes" />} />
      <Route path="/run" element={<LegacyThemeRedirect tab="axes" />} />
      <Route path="/monitor" element={<LegacyThemeRedirect tab="axes" />} />
      <Route path="/:theme" element={<AppShell />}>
        <Route index element={<Navigate to="axes" replace />} />
        <Route path="axes" element={<AxesPage />} />
        <Route path="select" element={<RedirectToAxesKeepSearch />} />
        <Route path="frames" element={<FramesPage />} />
        {/* Eval UI hidden until ready; keep route redirect so old links don't 404. */}
        <Route path="eval" element={<Navigate to="../axes" replace />} />
        <Route path="ops" element={<Navigate to="../axes" replace />} />
        <Route path="compare" element={<Navigate to="../axes" replace />} />
        <Route path="*" element={<Navigate to="axes" replace />} />
      </Route>
    </Routes>
  )
}

export default App
