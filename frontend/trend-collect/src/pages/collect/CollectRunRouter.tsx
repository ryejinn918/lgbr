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
import { PwcAdhocRunPage } from './PwcAdhocRunPage'
import { PwcDownloadPage } from './PwcDownloadPage'

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
  if (ctx.source === 'pwc' && ctx.stage === 'list' && ctx.means === 'search') {
    return <PwcAdhocRunPage />
  }
  if (
    ctx.source === 'pwc' &&
    ctx.stage === 'body' &&
    ctx.means === 'download'
  ) {
    return <PwcDownloadPage />
  }
  return <Navigate to={defaultCollectPath(ctx.source)} replace />
}
