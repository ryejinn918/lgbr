import {
  Navigate,
  NavLink,
  Route,
  Routes,
  useSearchParams,
} from 'react-router-dom'
import {
  CollectIndexRedirect,
  CollectShell,
  CollectSourceRedirect,
} from './components/CollectShell'
import { DocsShell } from './components/DocsShell'
import { CollectRunRouter } from './pages/collect/CollectRunRouter'
import { CollectTypesRouter } from './pages/collect/CollectTypesRouter'
import { DashboardPage } from './pages/DashboardPage'
import { ArticlesPage } from './pages/docs/ArticlesPage'
import { ReportsPage } from './pages/ReportsPage'
import './App.css'

function ReportsLegacyRedirect() {
  const [params] = useSearchParams()
  const q = params.toString()
  return (
    <Navigate
      to={q ? `/docs/reports/fnguide?${q}` : '/docs/reports/fnguide'}
      replace
    />
  )
}

function App() {
  return (
    <div className="monitor">
      <header className="app-shell">
        <p className="brand">fnguide-search-monitor</p>
        <nav className="app-nav" aria-label="주요 메뉴">
          <NavLink to="/" end>
            대시보드
          </NavLink>
          <NavLink to="/collect">수집</NavLink>
          <NavLink to="/docs">문서</NavLink>
        </nav>
      </header>
      <Routes>
        <Route path="/" element={<DashboardPage />} />

        <Route path="/collect" element={<CollectIndexRedirect />} />
        <Route path="/collect/:source" element={<CollectSourceRedirect />} />
        <Route
          path="/collect/:source/:stage/:means"
          element={<CollectShell />}
        >
          <Route index element={<CollectRunRouter />} />
          <Route path="types" element={<CollectTypesRouter />} />
        </Route>

        <Route path="/docs" element={<DocsShell />}>
          <Route index element={<Navigate to="articles" replace />} />
          <Route path="articles" element={<ArticlesPage />} />
          <Route path="reports/fnguide" element={<ReportsPage embedded />} />
          {/* legacy docs paths */}
          <Route
            path="fnguide"
            element={<Navigate to="/docs/reports/fnguide" replace />}
          />
          <Route
            path="other"
            element={<Navigate to="/docs/articles" replace />}
          />
          <Route
            path="other/body"
            element={<Navigate to="/docs/articles" replace />}
          />
        </Route>

        <Route
          path="/crawl"
          element={<Navigate to="/collect/fnguide/list/search" replace />}
        />
        <Route
          path="/types"
          element={
            <Navigate to="/collect/fnguide/list/search/types" replace />
          }
        />
        <Route path="/reports" element={<ReportsLegacyRedirect />} />
        <Route
          path="/other"
          element={<Navigate to="/collect/arg/list/feed" replace />}
        />
      </Routes>
    </div>
  )
}

export default App
