const path = require('path')

const root = __dirname
const searchMonitorDir = path.join(root, 'frontend', 'fnguide-search-monitor')
const consensusDir = path.join(root, 'frontend', 'fnguide-consensus')
const python = path.join(root, '.venv', 'bin', 'python')

module.exports = {
  apps: [
    {
      name: 'fnguide-search-monitor-api',
      cwd: root,
      script: python,
      args: '-m lgbr_api --host 127.0.0.1 --port 8787',
      interpreter: 'none',
      instances: 1,
      exec_mode: 'fork',
      autorestart: true,
      max_restarts: 10,
      min_uptime: '5s',
      // Wait for lifespan shutdown (request_stop + up to 60s) before SIGKILL.
      kill_timeout: 90000,
    },
    {
      name: 'fnguide-search-monitor',
      cwd: searchMonitorDir,
      script: './node_modules/vite/bin/vite.js',
      args: 'preview',
      interpreter: 'node',
      instances: 1,
      exec_mode: 'fork',
      autorestart: true,
      max_restarts: 10,
      min_uptime: '5s',
    },
    {
      name: 'fnguide-consensus',
      cwd: consensusDir,
      script: './node_modules/vite/bin/vite.js',
      args: 'preview',
      interpreter: 'node',
      instances: 1,
      exec_mode: 'fork',
      autorestart: true,
      max_restarts: 10,
      min_uptime: '5s',
    },
  ],
}
