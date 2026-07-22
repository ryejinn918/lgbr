import { NavLink, Route, Routes } from 'react-router-dom'
import { CrawlPage } from './pages/CrawlPage'
import { CrawlTypesPage } from './pages/CrawlTypesPage'
import { DashboardPage } from './pages/DashboardPage'
import { ReportsPage } from './pages/ReportsPage'
import './App.css'

function App() {
  return (
    <div className="monitor">
      <header className="app-shell">
        <p className="brand">fnguide-search-monitor</p>
        <nav className="app-nav" aria-label="주요 메뉴">
          <NavLink to="/" end>
            대시보드
          </NavLink>
          <NavLink to="/crawl">크롤</NavLink>
          <NavLink to="/types">타입</NavLink>
          <NavLink to="/reports">보고서</NavLink>
        </nav>
      </header>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/crawl" element={<CrawlPage />} />
        <Route path="/types" element={<CrawlTypesPage />} />
        <Route path="/reports" element={<ReportsPage />} />
      </Routes>
    </div>
  )
}

export default App
