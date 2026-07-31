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
import { getMediaSource } from '../../lib/mediaSources'
import { AccentureRunPage } from './AccentureRunPage'
import { BainRunPage } from './BainRunPage'
import { BcgRunPage } from './BcgRunPage'
import { DeloitteRunPage } from './DeloitteRunPage'
import { MckinseyRunPage } from './MckinseyRunPage'
import { EyRunPage } from './EyRunPage'
import { HbrRunPage } from './HbrRunPage'
import { HbrKoreaRunPage } from './HbrKoreaRunPage'
import { KpmgRunPage } from './KpmgRunPage'
import { PwcAdhocRunPage } from './PwcAdhocRunPage'
import { SourceAdhocRunPage } from './SourceAdhocRunPage'

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
    ctx.source === 'accenture' &&
    ctx.stage === 'list' &&
    ctx.means === 'search'
  ) {
    return <AccentureRunPage />
  }
  if (ctx.source === 'kpmg' && ctx.stage === 'list' && ctx.means === 'search') {
    return <KpmgRunPage />
  }
  if (ctx.source === 'ey' && ctx.stage === 'list' && ctx.means === 'search') {
    return <EyRunPage />
  }
  if (
    ctx.source === 'deloitte' &&
    ctx.stage === 'list' &&
    ctx.means === 'search'
  ) {
    return <DeloitteRunPage />
  }
  if (
    ctx.source === 'hbrkorea' &&
    ctx.stage === 'list' &&
    ctx.means === 'search'
  ) {
    return <HbrKoreaRunPage />
  }
  if (
    ctx.source === 'mckinsey' &&
    ctx.stage === 'list' &&
    ctx.means === 'search'
  ) {
    return <MckinseyRunPage />
  }
  if (ctx.source === 'bain' && ctx.stage === 'list' && ctx.means === 'search') {
    return <BainRunPage />
  }
  if (ctx.source === 'bcg' && ctx.stage === 'list' && ctx.means === 'search') {
    return <BcgRunPage />
  }
  if (ctx.source === 'hbr' && ctx.stage === 'list' && ctx.means === 'search') {
    return <HbrRunPage />
  }
  const media = getMediaSource(ctx.source)
  if (
    media &&
    !media.hasSearch &&
    ctx.stage === 'list' &&
    ctx.means === 'search'
  ) {
    return <SourceAdhocRunPage />
  }
  return <Navigate to={defaultCollectPath(ctx.source)} replace />
}
