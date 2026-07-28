import { Navigate, useOutletContext } from 'react-router-dom'
import {
  defaultCollectPath,
  type CollectMeans,
  type CollectSource,
  type CollectStage,
} from '../../lib/collectNav'
import { CrawlPage } from '../CrawlPage'
import { ArgFeedRunPage } from './ArgFeedRunPage'
import { ArgFetchBodyRunPage } from './ArgFetchBodyRunPage'
import { FnGuideDownloadPage } from './FnGuideDownloadPage'

type Ctx = {
  source: CollectSource
  stage: CollectStage
  means: CollectMeans
  supported: boolean
}

export function CollectRunRouter() {
  const ctx = useOutletContext<Ctx>()
  if (!ctx.supported) {
    return <Navigate to={defaultCollectPath(ctx.source)} replace />
  }

  if (ctx.source === 'fnguide' && ctx.stage === 'list' && ctx.means === 'search') {
    return <CrawlPage />
  }
  if (
    ctx.source === 'fnguide' &&
    ctx.stage === 'body' &&
    ctx.means === 'download'
  ) {
    return <FnGuideDownloadPage />
  }
  if (ctx.source === 'arg' && ctx.stage === 'list' && ctx.means === 'feed') {
    return <ArgFeedRunPage />
  }
  if (ctx.source === 'arg' && ctx.stage === 'body' && ctx.means === 'fetch') {
    return <ArgFetchBodyRunPage />
  }
  return <Navigate to={defaultCollectPath(ctx.source)} replace />
}
