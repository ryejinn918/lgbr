import { NavLink, Navigate, Outlet, useParams } from 'react-router-dom'
import {
  SOURCES,
  defaultCollectPath,
  defaultMeansPath,
  discoveryTypeLabel,
  isMeansSupported,
  isStageSupported,
  meansLabel,
  stageLabel,
  supportedMeans,
  supportedStages,
  type CollectMeans,
  type CollectSource,
  type CollectStage,
} from '../lib/collectNav'

function asSource(value: string | undefined): CollectSource | null {
  if (value === 'fnguide' || value === 'arg') return value
  return null
}

function asStage(value: string | undefined): CollectStage | null {
  if (value === 'list' || value === 'body') return value
  return null
}

function asMeans(
  stage: CollectStage,
  value: string | undefined,
): CollectMeans | null {
  if (stage === 'list' && (value === 'feed' || value === 'search')) return value
  if (stage === 'body' && (value === 'download' || value === 'fetch')) {
    return value
  }
  return null
}

export function CollectIndexRedirect() {
  return <Navigate to={defaultCollectPath('fnguide')} replace />
}

export function CollectSourceRedirect() {
  const source = asSource(useParams().source)
  if (!source) return <Navigate to={defaultCollectPath('fnguide')} replace />
  return <Navigate to={defaultCollectPath(source)} replace />
}

export function CollectShell() {
  const params = useParams()
  const source = asSource(params.source)
  const stage = asStage(params.stage)
  const means = stage ? asMeans(stage, params.means) : null

  if (!source) {
    return <Navigate to={defaultCollectPath('fnguide')} replace />
  }
  if (!stage || !means) {
    return <Navigate to={defaultCollectPath(source)} replace />
  }
  if (!isStageSupported(source, stage) || !isMeansSupported(source, stage, means)) {
    return <Navigate to={defaultCollectPath(source)} replace />
  }

  const stages = supportedStages(source)
  const meansOptions = supportedMeans(source, stage)
  const showTypes = stage === 'list'
  const showMeansNav = meansOptions.length > 1
  const showStageNav = stages.length > 1

  return (
    <div className="collect-shell">
      <header className="monitor-header">
        <h1>수집</h1>
        <p className="lede">
          매체별로 리스트 발굴(피드·검색)과 본문 채우기를 나눕니다. 리스트 발굴
          타입은 각 수단의 프로필입니다.
        </p>
      </header>

      <nav className="subnav" aria-label="수집 매체">
        {SOURCES.map((s) => (
          <NavLink
            key={s.id}
            to={defaultCollectPath(s.id)}
            className={() => (s.id === source ? 'active' : undefined)}
            end
          >
            {s.label}
          </NavLink>
        ))}
      </nav>

      {showStageNav ? (
        <nav className="subnav subnav-secondary" aria-label="수집 단계">
          {stages.map((st) => (
            <NavLink
              key={st}
              to={defaultMeansPath(source, st)}
              className={() => (st === stage ? 'active' : undefined)}
            >
              {stageLabel(st)}
            </NavLink>
          ))}
        </nav>
      ) : (
        <p className="section-note" style={{ margin: 0 }}>
          {stageLabel(stage)}
        </p>
      )}

      {showMeansNav ? (
        <nav className="subnav subnav-tertiary" aria-label="수집 수단">
          {meansOptions.map((m) => (
            <NavLink key={m} to={`/collect/${source}/${stage}/${m}`}>
              {meansLabel(m)}
            </NavLink>
          ))}
        </nav>
      ) : (
        <p className="section-note" style={{ margin: 0 }}>
          {meansLabel(means)}
        </p>
      )}

      {showTypes ? (
        <nav className="subnav subnav-action" aria-label="실행 또는 리스트 발굴 타입">
          <NavLink to={`/collect/${source}/list/${means}`} end>
            실행
          </NavLink>
          <NavLink to={`/collect/${source}/list/${means}/types`}>
            리스트 발굴 타입
          </NavLink>
        </nav>
      ) : null}

      <Outlet
        context={{
          source,
          stage,
          means,
          supported: true,
          typeLabel: discoveryTypeLabel(means),
        }}
      />
    </div>
  )
}
