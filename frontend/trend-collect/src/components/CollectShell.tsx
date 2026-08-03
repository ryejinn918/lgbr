import { NavLink, Navigate, Outlet, useParams } from 'react-router-dom'
import {
  SOURCES,
  defaultCollectPath,
  discoveryTypeLabel,
  findJob,
  isCollectSource,
  isMeansSupported,
  isStageSupported,
  jobHasSettings,
  jobPath,
  jobsFor,
  settingsPath,
  type CollectMeans,
  type CollectSource,
  type CollectStage,
} from '../lib/collectNav'

function asSource(value: string | undefined): CollectSource | null {
  return isCollectSource(value) ? value : null
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

  const jobs = jobsFor(source)
  const currentJob = findJob(source, stage, means)
  const showSettings = currentJob != null && jobHasSettings(currentJob)

  return (
    <div className="collect-shell">
      <header className="monitor-header">
        <h1>수집</h1>
        <p className="lede">매체를 고르고 검색을 실행합니다. 원문은 요약에만 쓰고 남기지 않습니다.</p>
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

      <nav className="subnav subnav-secondary" aria-label="수집 작업">
        {jobs.map((job) => (
          <NavLink
            key={job.id}
            to={jobPath(source, job)}
            className={() =>
              currentJob?.id === job.id ? 'active' : undefined
            }
          >
            {job.label}
          </NavLink>
        ))}
      </nav>

      {showSettings && currentJob ? (
        <nav className="subnav subnav-action" aria-label="실행 또는 설정">
          <NavLink to={jobPath(source, currentJob)} end>
            실행
          </NavLink>
          <NavLink to={settingsPath(source, currentJob)}>
            {currentJob.settingsLabel}
          </NavLink>
        </nav>
      ) : null}

      <Outlet
        context={{
          source,
          stage,
          means,
          supported: true,
          typeLabel: discoveryTypeLabel(means, source),
        }}
      />
    </div>
  )
}
