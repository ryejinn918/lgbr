import { NavLink, Outlet } from 'react-router-dom'

export function DocsShell() {
  return (
    <div className="docs-shell">
      <header className="monitor-header">
        <h1>문서</h1>
        <p className="lede">
          기사는 통합으로, 보고서는 매체별 탭으로 봅니다. 행을 누르면 아래에
          상세가 열립니다.
        </p>
      </header>

      <nav className="subnav" aria-label="문서 레인">
        <NavLink to="/docs/articles">기사</NavLink>
        <NavLink to="/docs/reports/fnguide">FnGuide 보고서</NavLink>
      </nav>

      <Outlet />
    </div>
  )
}
