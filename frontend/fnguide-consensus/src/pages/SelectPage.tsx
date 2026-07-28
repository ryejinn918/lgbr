import { Fragment, useEffect, useMemo, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { useConsensusStatus } from '../hooks/useConsensusStatus'
import { parseTheme, themePath } from '../lib/theme'
import { NAV, labelRunSlot, labelRunState } from '../lib/labels'
import type { InputReport, RunDoc, SelectCriteria } from '../types'
import { THEME_LABEL } from '../types'

function asCriteria(raw: unknown): SelectCriteria | null {
  if (!raw || typeof raw !== 'object') return null
  return raw as SelectCriteria
}

export function SelectPage() {
  const { theme: raw } = useParams()
  const theme = parseTheme(raw)
  const [searchParams] = useSearchParams()
  const runFromUrl = searchParams.get('run')
  const [inputs, setInputs] = useState<InputReport[]>([])
  const [poolQpCount, setPoolQpCount] = useState<number | null>(null)
  const [inputError, setInputError] = useState<string | null>(null)
  const [packRunId, setPackRunId] = useState<string | null>(runFromUrl)
  const [runDocs, setRunDocs] = useState<RunDoc[]>([])
  const [docsError, setDocsError] = useState<string | null>(null)

  const { status, history, continueRun, refresh } = useConsensusStatus(theme)
  const [continuingFull, setContinuingFull] = useState(false)

  const themeHistory = useMemo(
    () => history.filter((h) => h.theme === theme).slice(0, 2),
    [history, theme],
  )

  // status.run falls back to latest ended run when idle — only force-select when busy.
  const openThemeRun =
    status.run?.theme === theme &&
    (status.run.state === 'starting' ||
      status.run.state === 'active' ||
      status.run.state === 'stopping' ||
      status.run.state === 'awaiting')
      ? status.run
      : null

  const packRun = useMemo(() => {
    if (openThemeRun) return openThemeRun
    if (packRunId) {
      const hit = themeHistory.find((h) => h.id === packRunId)
      if (hit) return hit
    }
    return themeHistory[0] ?? null
  }, [openThemeRun, packRunId, themeHistory])

  const packCriteria = asCriteria(packRun?.criteria)
  const packIndex = packRun
    ? themeHistory.findIndex((h) => h.id === packRun.id)
    : -1
  const packLabel =
    packRun != null
      ? labelRunSlot(packIndex < 0 ? 0 : packIndex, packRun.state)
      : null
  const coreDocs = runDocs.filter((d) => d.role === 'selected')
  const biblioDocs = runDocs.filter((d) => d.role === 'fill_extra')
  const packDocs = [...coreDocs, ...biblioDocs]
  const selectOnly =
    (packRun?.state === 'ended' && packCriteria?.until === 'select') ||
    (packRun?.state === 'error' && packDocs.length > 0)
  const packById = useMemo(() => {
    const m = new Map<string, RunDoc>()
    for (const d of runDocs) {
      if (d.role === 'selected' || d.role === 'fill_extra') {
        m.set(d.report_id, d)
      }
    }
    return m
  }, [runDocs])
  const sortedInputs = useMemo(() => {
    const rank = (r: InputReport) => {
      const p = packById.get(r.id)
      if (p?.role === 'selected') return 0
      if (p?.role === 'fill_extra') return 1
      if (r.quality_pass === true) return 2
      return 3
    }
    return [...inputs].sort((a, b) => {
      const d = rank(a) - rank(b)
      if (d !== 0) return d
      return (a.title || '').localeCompare(b.title || '', 'ko')
    })
  }, [inputs, packById])
  const hasPackReview =
    !!packCriteria?.coverage_notes ||
    (!!packCriteria?.pillar_sketch && packCriteria.pillar_sketch.length > 0)

  useEffect(() => {
    setPoolQpCount(null)
    setPackRunId(runFromUrl)
    setRunDocs([])
    setDocsError(null)
  }, [theme, runFromUrl])

  useEffect(() => {
    let cancelled = false
    void fetch(`/api/consensus/inputs?theme=${theme}`)
      .then(async (r) => {
        const d = await r.json()
        if (!r.ok || !d.ok) throw new Error(d.message || `HTTP ${r.status}`)
        if (!cancelled) {
          setInputs(d.items ?? [])
          const qp = d.criteria?.quality_pass_count
          setPoolQpCount(typeof qp === 'number' ? qp : null)
          setInputError(null)
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setInputError(e instanceof Error ? e.message : String(e))
          setPoolQpCount(null)
        }
      })
    return () => {
      cancelled = true
    }
  }, [theme])

  useEffect(() => {
    const runId = packRun?.id
    if (!runId) {
      setRunDocs([])
      setDocsError(null)
      return
    }
    let cancelled = false
    const load = () => {
      void fetch(`/api/consensus/runs/${runId}/docs`)
        .then(async (r) => {
          const d = await r.json()
          if (!r.ok || !d.ok) throw new Error(d.message || `HTTP ${r.status}`)
          if (!cancelled) {
            setRunDocs((d.items ?? []) as RunDoc[])
            setDocsError(null)
          }
        })
        .catch((e) => {
          if (!cancelled) {
            setDocsError(e instanceof Error ? e.message : String(e))
          }
        })
    }
    load()
    const busy =
      packRun.state === 'starting' ||
      packRun.state === 'active' ||
      packRun.state === 'stopping'
    const t = busy ? window.setInterval(load, 3_000) : 0
    return () => {
      cancelled = true
      if (t) window.clearInterval(t)
    }
  }, [packRun?.id, packRun?.state])

  return (
    <>
      <header className="monitor-header">
        <h1>
          {THEME_LABEL[theme]} · 보고서 선별
        </h1>
        <p className="lede">
          컨센서스에 쓸 보고서를 어떻게 골랐는지 봅니다. 축 가르기·시작은{' '}
          <Link className="text-link" to={themePath(theme, 'axes')}>
            {NAV.axes}
          </Link>{' '}
          메뉴에서 합니다.
        </p>
      </header>

      {status.run?.theme === theme && status.run.state === 'awaiting' && (
        <section className="panel">
          <p className="section-note">
            축 확인 대기 중입니다. 선별은 축을 확정한 뒤에 진행됩니다.{' '}
            <Link className="text-link" to={themePath(theme, 'axes')}>
              {NAV.axes}
            </Link>
            에서 확인하세요.
          </p>
        </section>
      )}

      {selectOnly && packRun && packDocs.length > 0 && (
        <section className="panel">
          <p className="section-note">
            이 실행은 선별까지만 진행했습니다. 같은 팩으로 논지(요약·골격·살붙임)를
            이어서 만들 수 있습니다.
          </p>
          <div className="chip-row" style={{ gap: '0.5rem', marginTop: '0.75rem' }}>
            <button
              type="button"
              className="btn"
              disabled={!status.can_start || continuingFull}
              onClick={() => {
                if (!packRun.id || !status.can_start) return
                if (
                  !window.confirm(
                    '이 선별 팩을 유지한 채 요약·골격·살 붙인 논지를 이어서 만들까요?',
                  )
                ) {
                  return
                }
                setContinuingFull(() => true)
                void continueRun(packRun.id, { resume_from: 'doc' })
                  .then(() => refresh())
                  .catch((e) =>
                    window.alert(e instanceof Error ? e.message : '계속 실패'),
                  )
                  .finally(() => setContinuingFull(() => false))
              }}
            >
              {continuingFull ? '진행 중…' : '이 선별로 논지까지 계속'}
            </button>
            <Link className="btn ghost" to={themePath(theme, 'frames')}>
              {NAV.frames} 보기
            </Link>
            {!status.can_start && (
              <span className="section-note">
                다른 작업이 열려 있어 지금은 이을 수 없습니다.
              </span>
            )}
          </div>
        </section>
      )}

      <section className="panel">
        <div className="section-head">
          <h2>이번 선별 결과</h2>
          <p className="section-note">
            {packRun && packLabel
              ? `${packLabel} · ${labelRunState(packRun.state)}${
                  selectOnly ? ' · 선별까지만' : ''
                } · 주요 ${coreDocs.length} · 보조 ${biblioDocs.length}`
              : '이 섹터 실행 이력이 없습니다. 컨센서스를 시작하면 여기에 선별 결과가 남습니다.'}
          </p>
        </div>
        {themeHistory.length > 1 && (
          <div className="chip-row">
            {themeHistory.map((h, i) => (
              <button
                key={h.id}
                type="button"
                className={`chip ${packRun?.id === h.id ? 'active' : ''}`}
                onClick={() => setPackRunId(h.id)}
              >
                {labelRunSlot(i, h.state)}
              </button>
            ))}
          </div>
        )}
        {docsError && <p className="error-line">{docsError}</p>}
        {hasPackReview && (
          <div className="select-review">
            <h3>선별 이유</h3>
            {packCriteria?.coverage_notes ? (
              <p className="select-review-body">
                {packCriteria.coverage_notes}
              </p>
            ) : null}
            {packCriteria?.pillar_sketch &&
            packCriteria.pillar_sketch.length > 0 ? (
              <>
                <p className="section-note">다룰 주제</p>
                <ul className="select-review-list">
                  {packCriteria.pillar_sketch.map((p, i) => (
                    <li key={`${i}-${p}`}>{p}</li>
                  ))}
                </ul>
              </>
            ) : null}
          </div>
        )}
        {packRun && packDocs.length === 0 && !docsError && (
          <p className="section-note">
            아직 보고서 선별 전입니다. 선별이 끝나면 주요문헌·보조문헌 목록과
            이유가 채워집니다.
          </p>
        )}
        {packDocs.length > 0 && (
          <table className="data-table">
            <thead>
              <tr>
                <th className="col-role">구분</th>
                <th>제목</th>
                <th>증권사</th>
                <th>쪽</th>
                <th>이유</th>
              </tr>
            </thead>
            <tbody>
              {packDocs.map((d, i) => {
                const role = d.role === 'fill_extra' ? 'biblio' : 'core'
                const prev = i > 0 ? packDocs[i - 1] : null
                const prevRole =
                  prev?.role === 'fill_extra'
                    ? 'biblio'
                    : prev
                      ? 'core'
                      : null
                const showGroup = role !== prevRole
                return (
                  <Fragment key={d.report_id}>
                    {showGroup && (
                      <tr className={`input-group-row role-${role}`}>
                        <td colSpan={5}>
                          {role === 'core'
                            ? `주요문헌 · ${coreDocs.length}건`
                            : `보조문헌 · ${biblioDocs.length}건`}
                        </td>
                      </tr>
                    )}
                    <tr className={`input-row role-${role}`}>
                      <td className="col-role">
                        <span className={`role-badge role-${role}`}>
                          {role === 'core' ? '주요' : '보조'}
                        </span>
                      </td>
                      <td>
                        <a
                          className="text-link"
                          href={`/api/reports/${d.report_id}/file`}
                          download
                          title="보고서 받기"
                        >
                          {d.title}
                        </a>
                      </td>
                      <td>{d.provider ?? '—'}</td>
                      <td>{d.page_count ?? '—'}</td>
                      <td title={d.select_why ?? undefined}>
                        {d.select_why ?? '—'}
                      </td>
                    </tr>
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        )}
      </section>

      <section className="panel">
        <div className="section-head">
          <h2>후보 보고서</h2>
          <p className="section-note">
            최근 3개월 · 후보 {inputs.length}
            {poolQpCount != null ? ` · 품질 통과 ${poolQpCount}` : ''}
            {packDocs.length > 0
              ? ` · 위 선별과 동일: 주요 ${coreDocs.length} · 보조 ${biblioDocs.length}`
              : ` · 선별은 ${NAV.axes}에서 축 확정 후`}
          </p>
        </div>
        {inputError && <p className="error-line">{inputError}</p>}
        <table className="data-table">
          <thead>
            <tr>
              <th className="col-role">구분</th>
              <th>제목</th>
              <th>출처</th>
              <th>증권사</th>
              <th>일자</th>
              <th>쪽</th>
              <th className="col-quality">품질</th>
              <th>이유</th>
            </tr>
          </thead>
          <tbody>
            {sortedInputs.map((r) => {
              const packed = packById.get(r.id)
              const kind =
                packed?.role === 'selected'
                  ? 'core'
                  : packed?.role === 'fill_extra'
                    ? 'biblio'
                    : r.quality_pass === true
                      ? 'pool'
                      : 'omit'
              const badge =
                kind === 'core'
                  ? '주요'
                  : kind === 'biblio'
                    ? '보조'
                    : kind === 'pool'
                      ? '후보'
                      : '미달'
              const why = packed?.select_why ?? null
              const rowClass =
                kind === 'core'
                  ? 'input-row role-core'
                  : kind === 'biblio'
                    ? 'input-row role-biblio'
                    : kind === 'pool'
                      ? 'input-row'
                      : 'input-row role-omit'
              return (
                <tr key={r.id} className={rowClass}>
                  <td className="col-role">
                    <span className={`role-badge role-${kind}`}>{badge}</span>
                  </td>
                  <td>
                    <a
                      className="text-link"
                      href={`/api/reports/${r.id}/file`}
                      download
                      title="보고서 받기"
                    >
                      {r.title}
                    </a>
                  </td>
                  <td>{r.theme_tag ?? '—'}</td>
                  <td>{r.provider ?? '—'}</td>
                  <td>{r.published_at ?? '—'}</td>
                  <td>{r.page_count ?? '—'}</td>
                  <td className="col-quality">
                    {r.quality_pass === true
                      ? '통과'
                      : r.quality_pass === false
                        ? (
                            <>
                              미달/
                              <wbr />
                              {r.quality_scope ?? '?'}
                            </>
                          )
                        : '대기'}
                  </td>
                  <td title={why ?? undefined}>{why ?? '—'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </section>
    </>
  )
}
