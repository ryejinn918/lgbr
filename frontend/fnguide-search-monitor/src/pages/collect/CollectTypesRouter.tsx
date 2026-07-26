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
  return <Navigate to={defaultCollectPath(ctx.source)} replace />
}
