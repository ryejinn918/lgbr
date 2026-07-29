import { Navigate, useOutletContext } from 'react-router-dom'
import {
  defaultCollectPath,
  type CollectMeans,
  type CollectSource,
  type CollectStage,
} from '../../lib/collectNav'
import { ArgFeedTypesPage } from './ArgFeedTypesPage'
import { SearchTypesPage } from './SearchTypesPage'

type Ctx = {
  source: CollectSource
  stage: CollectStage
  means: CollectMeans
  supported: boolean
}

export function CollectTypesRouter() {
  const ctx = useOutletContext<Ctx>()
  if (ctx.stage !== 'list' || !ctx.supported) {
    return <Navigate to={defaultCollectPath(ctx.source)} replace />
  }

  if (ctx.source === 'fnguide' && ctx.means === 'search') {
    return <SearchTypesPage />
  }
  if (ctx.source === 'arg' && ctx.means === 'feed') {
    return <ArgFeedTypesPage />
  }
  if (ctx.source === 'pwc' && ctx.means === 'search') {
    return (
      <section className="panel">
        <p className="badge-label">리스트 발굴 타입 · 검색</p>
        <p className="account-line">
          PwC는 아직 검색 프로필이 없습니다. Phase 1에서는 애드혹 브라우저로
          페이지를 분석합니다.
        </p>
      </section>
    )
  }
  return <Navigate to={defaultCollectPath(ctx.source)} replace />
}
