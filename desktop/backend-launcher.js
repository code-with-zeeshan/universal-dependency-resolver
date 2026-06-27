const { spawn } = require('child_process')
const http = require('http')
const net = require('net')
const crypto = require('crypto')

function findFreePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer()
    server.listen(0, '127.0.0.1', () => {
      const port = server.address().port
      server.close(() => resolve(port))
    })
    server.on('error', reject)
  })
}

function generateSecretKey() {
  return crypto.randomBytes(48).toString('hex')
}

function getEnv(port, extraEnv = {}) {
  return {
    ...process.env,
    UDR_PORT: String(port),
    UDR_HOST: '127.0.0.1',
    UDR_DESKTOP: 'true',
    PYTHONUNBUFFERED: '1',
    SECRET_KEY: process.env.SECRET_KEY || generateSecretKey(),
    ...extraEnv,
  }
}

function waitForServer(url, maxRetries = 30, onCrashed = null) {
  return new Promise((resolve, reject) => {
    let retries = 0
    const check = () => {
      if (onCrashed && onCrashed()) {
        reject(new Error('Backend process crashed'))
        return
      }
      http.get(url, () => resolve()).on('error', () => {
        retries++
        if (retries >= maxRetries) {
          reject(new Error('Server did not start in time'))
        } else {
          setTimeout(check, 1000)
        }
      })
    }
    check()
  })
}

function spawnBackend(cmd, args, port, isBinary, cwd) {
  return new Promise((resolve, reject) => {
    let crashed = false

    const allArgs = args.length > 0
      ? [...args, '--host', '127.0.0.1', '--port', String(port)]
      : [String(port)]

    const proc = spawn(cmd, allArgs, {
      cwd,
      env: getEnv(port),
      stdio: ['ignore', 'pipe', 'pipe'],
    })

    let started = false

    function onOutput(data) {
      const msg = data.toString()
      if (!started && (msg.includes('Uvicorn running') || msg.includes('Application startup complete') || msg.includes('Uvicorn'))) {
        started = true
        resolve({ process: proc, crashed: () => crashed })
      }
    }

    proc.stdout.on('data', (data) => {
      console.log('[backend:out]', data.toString().trimEnd())
      onOutput(data)
    })

    proc.stderr.on('data', (data) => {
      const msg = data.toString()
      console.log('[backend:err]', msg.trimEnd())
      onOutput(data)
    })

    proc.on('error', (err) => {
      crashed = true
      if (!started) reject(err)
    })

    proc.on('exit', (code) => {
      crashed = true
      if (!started) reject(new Error(`Backend exited unexpectedly with code ${code}`))
    })

    setTimeout(() => {
      if (!started) resolve({ process: proc, crashed: () => crashed })
    }, 60000)
  })
}

function getPlatformHint(isMac, isWin) {
  const hints = []
  if (isMac) {
    hints.push('- If the app is blocked by macOS, go to System Settings → Privacy & Security and click "Open Anyway"')
  }
  if (!isWin) {
    hints.push('- Ensure the binary has execute permission: chmod +x <path-to-backend>')
  }
  if (isWin) {
    hints.push('- The bundled backend may be blocked by antivirus. Try adding an exclusion for the app directory.')
  }
  return hints.length ? '\n' + hints.join('\n') : ''
}

module.exports = {
  findFreePort,
  generateSecretKey,
  getEnv,
  spawnBackend,
  waitForServer,
  getPlatformHint,
}
