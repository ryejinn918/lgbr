import { NIKKEI_SECTIONS } from '../../lib/nikkeiSections'

export function NikkeiFeedTypesPage() {
  return (
    <section className="panel">
      <div className="section-head">
        <h2>섹션</h2>
        <span className="section-note">Nikkei · 피드 · 설정</span>
      </div>
      <p className="lede" style={{ marginTop: 0 }}>
        분야별 速報 카테고리에 대응하는 wor.jp RSS(비공식 미러)로 목록을
        가져옵니다. 본문은 별도 「본문」단계에서 로그인 세션으로 채웁니다.
      </p>
      <table className="report-table">
        <thead>
          <tr>
            <th className="col-title">섹션</th>
            <th className="col-provider">카테고리</th>
            <th className="col-rpt">RSS</th>
          </tr>
        </thead>
        <tbody>
          {NIKKEI_SECTIONS.map((sec) => (
            <tr key={sec.id}>
              <td className="col-title report-title">
                {sec.label}
                <div className="muted" style={{ fontSize: '0.85em' }}>
                  {sec.id}
                </div>
              </td>
              <td className="col-provider">
                <a href={sec.categoryUrl} target="_blank" rel="noreferrer">
                  {sec.categoryUrl.replace('https://www.nikkei.com', '')}
                </a>
              </td>
              <td className="col-rpt">
                <a href={sec.rssUrl} target="_blank" rel="noreferrer">
                  {sec.id}.rdf
                </a>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
