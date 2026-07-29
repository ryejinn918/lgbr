import { NavLink, Outlet } from 'react-router-dom'

export function DocsShell() {
  return (
    <div className="docs-shell">
      <header className="monitor-header">
        <h1>문서</h1>
        <p className="lede">
          기사 통합·보고서 통합으로 모으고, 매체 탭으로 나눌 수 있습니다. 행을
          누르면 아래에 상세가 열립니다.
        </p>
      </header>

      <nav className="subnav" aria-label="문서 레인">
        <NavLink to="/docs/articles">기사 통합</NavLink>
        <NavLink to="/docs/reports" end>
          보고서 통합
        </NavLink>
        <NavLink to="/docs/reports/fnguide">FnGuide</NavLink>
        <NavLink to="/docs/reports/pwc">PwC</NavLink>
      </nav>

      <Outlet />
    </div>
  )
}
