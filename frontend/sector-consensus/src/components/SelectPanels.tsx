import { Fragment, useEffect, useMemo, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { useConsensusStatusContext } from '../hooks/ConsensusStatusContext'
import {
  BLOCKED_BY_OPEN_RUN,
  labelRunSlot,
  labelRunState,
  labelThemes,
} from '../lib/labels'
import { isLiveState, openRunForTheme } from '../lib/runState'
import { formatPubDate } from '../lib/format'
import { parseTheme } from '../lib/theme'
import type { InputReport, RunDoc, SelectCriteria } from '../types'

function asCriteria(raw: unknown): SelectCriteria | null {
  if (!raw || typeof raw !== 'object') return null
  return raw as SelectCriteria
}

/** Report selection review + candidate pool (embedded under axes). */
export function SelectPanels() {
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

  const { status, history, continueRun, refresh } = useConsensusStatusContext()
  const [continuingFull, setContinuingFull] = useState(false)

  const themeHistory = useMemo(
    () => history.filter((h) => h.theme === theme).slice(0, 2),
    [history, theme],
  )

  const openThemeRun = openRunForTheme(status, theme)

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
  const sortedInputs = useMemo(() => {
    const rank = (r: InputReport) => (r.quality_pass === true ? 0 : 1)
    return [...inputs].sort((a, b) => {
      const d = rank(a) - rank(b)
      if (d !== 0) return d
      return (a.title || '').localeCompare(b.title || '', 'ko')
    })
  }, [inputs])
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
    const t = isLiveState(packRun.state) ? window.setInterval(load, 3_000) : 0
    return () => {
      cancelled = true
      if (t) window.clearInterval(t)
    }
  }, [packRun?.id, packRun?.state])

  return (
    <>
      {selectOnly && packRun && packDocs.length > 0 && (
        <section className="panel">
          <button
            type="button"
            className="btn"
            disabled={!status.can_start || continuingFull}
            onClick={() => {
              if (!packRun.id || !status.can_start) return
              if (
                !window.confirm(
                  '이 선별 팩을 유지한 채 요약·골격·보고서를 이어서 만들까요?',
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
            {continuingFull ? '진행 중…' : '이 선별로 컨센서스까지 계속'}
          </button>
          {!status.can_start ? (
            <p className="section-note">{BLOCKED_BY_OPEN_RUN}</p>
          ) : null}
        </section>
      )}

      <section className="panel">
        <div className="section-head">
          <h2>보고서 선별</h2>
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
                <th>선정이유</th>
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
                        <span className="text-link" title={d.title}>
                          {d.title}
                        </span>
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
            {' · AI 축 선정에 쓰는 품질감사 요약'}
          </p>
        </div>
        {inputError && <p className="error-line">{inputError}</p>}
        <table className="data-table pool-table">
          <thead>
            <tr>
              <th className="col-title">제목</th>
              <th className="col-theme">테마</th>
              <th className="col-provider">증권사</th>
              <th className="col-date">일자</th>
              <th className="col-pages">쪽</th>
              <th className="col-quality">품질</th>
              <th className="col-framework">요약</th>
            </tr>
          </thead>
          <tbody>
            {sortedInputs.map((r) => {
              const rowClass =
                r.quality_pass === true ? 'input-row' : 'input-row role-omit'
              const themeLabels = labelThemes(
                r.themes?.length
                  ? r.themes
                  : r.theme_tag
                    ? [r.theme_tag]
                    : [],
              )
              const summaryTip = [r.topic, r.framework_summary, r.rationale]
                .filter(Boolean)
                .join('\n\n')
              return (
                <tr key={r.id} className={rowClass}>
                  <td className="col-title">
                    <span className="text-link cell-clamp" title={r.title}>
                      {r.title}
                    </span>
                  </td>
                  <td className="col-theme" title={themeLabels}>
                    {themeLabels}
                  </td>
                  <td className="col-provider" title={r.provider ?? undefined}>
                    {r.provider ?? '—'}
                  </td>
                  <td className="col-date" title={r.published_at ?? undefined}>
                    {formatPubDate(r.published_at)}
                  </td>
                  <td className="col-pages">{r.page_count ?? '—'}</td>
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
                  <td
                    className="col-framework"
                    title={summaryTip || undefined}
                  >
                    <span className="cell-clamp">
                      {r.framework_summary ?? '—'}
                    </span>
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
