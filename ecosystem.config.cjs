const path = require('path')

const root = __dirname
const trendCollectDir = path.join(root, 'frontend', 'trend-collect')
const consensusDir = path.join(root, 'frontend', 'sector-consensus')
const python = path.join(root, '.venv', 'bin', 'python')

module.exports = {
  apps: [
    {
      name: 'lgbr-api',
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
      name: 'trend-collect',
      cwd: trendCollectDir,
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
      name: 'sector-consensus',
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
