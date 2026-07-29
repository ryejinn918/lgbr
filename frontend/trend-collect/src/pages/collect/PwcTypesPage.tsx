import { Link } from 'react-router-dom'
import { PWC_CATALOGS } from '../../lib/pwcCatalogs'

/** PwC list catalogs — which hub/collection to crawl (not FnGuide search profiles). */
export function PwcTypesPage() {
  return (
    <section className="panel">
      <div className="section-head">
        <h2>목록 · 한국 / 국제</h2>
        <span className="section-note">PwC · 검색</span>
      </div>
      <p className="lede" style={{ marginTop: 0 }}>
        FnGuide의 검색 프로필과 달리, 여기서는 어느 지역 목록(카탈로그)을
        돌릴지 고릅니다. 실행 화면에서 목록을 선택한 뒤 검색을 돌리면
        됩니다.
      </p>
      <table className="report-table">
        <thead>
          <tr>
            <th className="col-title">목록</th>
            <th className="col-provider">허브</th>
            <th className="col-pages">페이지 크기</th>
            <th className="col-rpt">비고</th>
          </tr>
        </thead>
        <tbody>
          {PWC_CATALOGS.map((c) => (
            <tr key={c.id}>
              <td className="col-title report-title">{c.label}</td>
              <td className="col-provider">
                <a
                  className="report-file-link report-original-link"
                  href={c.hubUrl}
                  target="_blank"
                  rel="noreferrer"
                >
                  {c.hubUrl.replace(/^https?:\/\//, '')}
                </a>
              </td>
              <td className="col-pages mono">{c.pageSize}</td>
              <td className="col-rpt">{c.note}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="account-line" style={{ marginTop: '0.75rem' }}>
        실행:{' '}
        <Link to="/collect/pwc/list/search">검색 실행</Link>
        {' · '}
        문서: <Link to="/docs/reports/pwc">PwC 보고서</Link>
      </p>
    </section>
  )
}
