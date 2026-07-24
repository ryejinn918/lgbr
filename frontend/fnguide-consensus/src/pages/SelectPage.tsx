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
  const [selectedCount, setSelectedCount] = useState(0)
  const [secondaryCount, setSecondaryCount] = useState(0)
  const [poolQpCount, setPoolQpCount] = useState<number | null>(null)
  const [inputError, setInputError] = useState<string | null>(null)
  const [packRunId, setPackRunId] = useState<string | null>(runFromUrl)
  const [runDocs, setRunDocs] = useState<RunDoc[]>([])
  const [docsError, setDocsError] = useState<string | null>(null)

  const { status, history } = useConsensusStatus(theme)

  const themeHistory = useMemo(
    () => history.filter((h) => h.theme === theme),
    [history, theme],
  )

  const openThemeRun = status.run?.theme === theme ? status.run : null

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
          setSelectedCount(d.selected_count ?? 0)
          setSecondaryCount(d.secondary_count ?? 0)
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
          {THEME_LABEL[theme]} · {NAV.select}
        </h1>
        <p className="lede">
          후보를 걸러 팩(골격·참고)에 넣은 결과와 후보 풀을 확인합니다. 생성은{' '}
          <Link className="text-link" to={themePath(theme, 'ops')}>
            {NAV.ops}
          </Link>
          에서 합니다.
        </p>
      </header>

      <section className="panel">
        <div className="section-head">
          <h2>실행 선별</h2>
          <p className="section-note">
            {packRun && packLabel
              ? `${packLabel} · ${labelRunState(packRun.state)} · 골격 ${coreDocs.length} · 참고 ${biblioDocs.length}`
              : '이 섹터 실행 이력이 없습니다. 생성 시작하면 여기에 선별 결과가 남습니다.'}
          </p>
        </div>
        {themeHistory.length > 1 && (
          <div className="chip-row">
            {themeHistory.slice(0, 8).map((h, i) => (
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
            <h3>선별 심사평</h3>
            {packCriteria?.coverage_notes ? (
              <p className="select-review-body">
                {packCriteria.coverage_notes}
              </p>
            ) : null}
            {packCriteria?.pillar_sketch &&
            packCriteria.pillar_sketch.length > 0 ? (
              <>
                <p className="section-note">축 초안</p>
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
            아직 선별 단계 전입니다. 선별이 끝나면 골격/참고와 사유가 채워집니다.
          </p>
        )}
        {packDocs.length > 0 && (
          <table className="data-table">
            <thead>
              <tr>
                <th>역할</th>
                <th>제목</th>
                <th>증권사</th>
                <th>쪽</th>
                <th>사유</th>
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
                            ? `골격논지 (frame) · ${coreDocs.length}건`
                            : `참고문헌 (fill) · ${biblioDocs.length}건`}
                        </td>
                      </tr>
                    )}
                    <tr className={`input-row role-${role}`}>
                      <td>
                        <span className={`role-badge role-${role}`}>
                          {role === 'core' ? '골격' : '참고'}
                        </span>
                      </td>
                      <td>{d.title}</td>
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
          <h2>{theme === 'ai' ? '후보 풀' : '입력 리포트'}</h2>
          <p className="section-note">
            {theme === 'ai' ? (
              <>
                후보 {inputs.length}
                {poolQpCount != null ? ` · 품질통과 ${poolQpCount}` : ''}
                {' · '}선별은 {NAV.ops} 생성 시작 시
              </>
            ) : (
              <>
                선별 {selectedCount}
                {secondaryCount > 0 ? ` · 참고 ${secondaryCount}` : ''} /{' '}
                {inputs.length}
              </>
            )}
          </p>
        </div>
        {inputError && <p className="error-line">{inputError}</p>}
        <table className="data-table">
          <thead>
            <tr>
              {theme !== 'ai' && <th>역할</th>}
              <th>제목</th>
              <th>출처</th>
              <th>증권사</th>
              <th>일자</th>
              <th>쪽</th>
              <th>품질</th>
              {theme !== 'ai' && <th>사유</th>}
            </tr>
          </thead>
          <tbody>
            {inputs.map((r) => {
              if (theme === 'ai') {
                return (
                  <tr
                    key={r.id}
                    className={
                      r.quality_pass === true
                        ? 'input-row'
                        : 'input-row role-omit'
                    }
                  >
                    <td>{r.title}</td>
                    <td>{r.theme_tag ?? '—'}</td>
                    <td>{r.provider ?? '—'}</td>
                    <td>{r.published_at ?? '—'}</td>
                    <td>{r.page_count ?? '—'}</td>
                    <td>
                      {r.quality_pass === true
                        ? '통과'
                        : r.quality_pass === false
                          ? `미달/${r.quality_scope ?? '?'}`
                          : '대기'}
                    </td>
                  </tr>
                )
              }
              const role = r.will_select
                ? 'core'
                : r.will_fill_extra
                  ? 'biblio'
                  : 'omit'
              return (
                <tr key={r.id} className={`input-row role-${role}`}>
                  <td>
                    <span className={`role-badge role-${role}`}>
                      {role === 'core'
                        ? '골격'
                        : role === 'biblio'
                          ? '참고'
                          : '제외'}
                    </span>
                  </td>
                  <td>{r.title}</td>
                  <td>{r.theme_tag ?? '—'}</td>
                  <td>{r.provider ?? '—'}</td>
                  <td>{r.published_at ?? '—'}</td>
                  <td>{r.page_count ?? '—'}</td>
                  <td>
                    {r.quality_pass === true
                      ? '통과'
                      : r.quality_pass === false
                        ? `미달/${r.quality_scope ?? '?'}`
                        : '대기'}
                  </td>
                  <td title={r.select_why ?? r.exclude_reason ?? undefined}>
                    {role !== 'omit'
                      ? (r.select_why ?? '—')
                      : (r.exclude_reason ?? '—')}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </section>
    </>
  )
}
