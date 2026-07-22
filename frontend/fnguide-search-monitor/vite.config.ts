import {
  defineConfig,
  loadEnv,
  type Connect,
  type Plugin,
  type PluginOption,
} from 'vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'
import { timingSafeEqual } from 'node:crypto'

function safeEqual(a: string, b: string): boolean {
  const ab = Buffer.from(a)
  const bb = Buffer.from(b)
  if (ab.length !== bb.length) return false
  return timingSafeEqual(ab, bb)
}

function basicAuthPlugin(user: string, password: string): Plugin {
  const realm = 'fnguide-search-monitor'

  const middleware: Connect.NextHandleFunction = (req, res, next) => {
    const header = req.headers.authorization
    if (header?.startsWith('Basic ')) {
      const decoded = Buffer.from(header.slice(6), 'base64').toString('utf8')
      const sep = decoded.indexOf(':')
      const u = sep >= 0 ? decoded.slice(0, sep) : ''
      const p = sep >= 0 ? decoded.slice(sep + 1) : ''
      if (safeEqual(u, user) && safeEqual(p, password)) {
        next()
        return
      }
    }
    res.statusCode = 401
    res.setHeader('WWW-Authenticate', `Basic realm="${realm}", charset="UTF-8"`)
    res.end('Unauthorized')
  }

  return {
    name: 'lgbr-basic-auth',
    configureServer(server) {
      server.middlewares.use(middleware)
    },
    configurePreviewServer(server) {
      server.middlewares.use(middleware)
    },
  }
}

export default defineConfig(({ mode }) => {
  // Root .env (repo) + local frontend env
  const rootEnv = loadEnv(mode, path.resolve(__dirname, '../..'), '')
  const localEnv = loadEnv(mode, __dirname, '')
  const env = { ...rootEnv, ...localEnv }

  const apiKey = env.LGBR_API_KEY || ''
  const uiUser = env.LGBR_UI_USER || 'lgbr'
  const uiPassword = env.LGBR_UI_PASSWORD || ''

  const plugins: PluginOption[] = [react()]
  if (uiPassword) {
    plugins.push(basicAuthPlugin(uiUser, uiPassword))
  } else {
    console.warn(
      '[vite] LGBR_UI_PASSWORD unset — Basic Auth disabled (local only)',
    )
  }

  const apiProxy = {
    '/api': {
      target: 'http://127.0.0.1:8787',
      changeOrigin: true,
      headers: apiKey ? { 'X-API-Key': apiKey } : {},
    },
  } as const

  return {
    plugins,
    server: {
      host: '127.0.0.1',
      port: 8788,
      strictPort: true,
      allowedHosts: ['lgbrwsl.tail700203.ts.net'],
      proxy: apiProxy,
    },
    preview: {
      host: '127.0.0.1',
      port: 8788,
      strictPort: true,
      allowedHosts: ['lgbrwsl.tail700203.ts.net'],
      proxy: apiProxy,
    },
  }
})
