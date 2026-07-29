export function ArgFeedTypesPage() {
  return (
    <section className="panel">
      <div className="section-head">
        <h2>타입</h2>
        <span className="section-note">ARG · 피드 · 설정</span>
      </div>
      <p className="lede" style={{ marginTop: 0 }}>
        무엇을 구독할지 정합니다. 카테고리·섹션 단위 타입은 나중에 여기에
        추가합니다.
      </p>
      <table className="report-table">
        <thead>
          <tr>
            <th className="col-title">타입</th>
            <th className="col-provider">범위</th>
            <th className="col-rpt">상태</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td className="col-title report-title">전체</td>
            <td className="col-provider">
              articleList · view_type=sm (전 섹션)
            </td>
            <td className="col-rpt">기본</td>
          </tr>
        </tbody>
      </table>
    </section>
  )
}
