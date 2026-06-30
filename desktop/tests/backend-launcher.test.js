const { describe, it } = require('node:test')
const assert = require('node:assert')
const path = require('path')
const fs = require('fs')
const net = require('net')
const http = require('http')
const os = require('os')
const launcher = require('../backend-launcher')

const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'udr-test-'))

const serverScript = path.join(tmpDir, 'server.js')
fs.writeFileSync(serverScript, `
const http = require('http')
const port = process.argv[2] || 0
http.createServer((req, res) => {
  res.writeHead(200, { 'Content-Type': 'application/json' })
  res.end(JSON.stringify({ status: 'ok' }))
}).listen(port, () => {
  console.log('Uvicorn running on http://127.0.0.1:' + port)
})
`)

const startupScript = path.join(tmpDir, 'startup.js')
fs.writeFileSync(startupScript, `
console.log('Application startup complete')
setInterval(() => {}, 10000)
`)

const exitScript = path.join(tmpDir, 'exit.js')
fs.writeFileSync(exitScript, `
process.exit(1)
`)

describe('findFreePort', () => {
  it('returns a valid port number', async () => {
    const port = await launcher.findFreePort()
    assert.strictEqual(typeof port, 'number')
    assert.ok(port > 0 && port < 65536)
  })

  it('returns a port that is actually free', async () => {
    const port = await launcher.findFreePort()
    await new Promise((resolve, reject) => {
      const server = net.createServer()
      server.listen(port, '127.0.0.1', () => {
        server.close(resolve)
      })
      server.on('error', reject)
    })
  })
})

describe('generateSecretKey', () => {
  it('returns a hex string of 96 characters', () => {
    const key = launcher.generateSecretKey()
    assert.strictEqual(typeof key, 'string')
    assert.strictEqual(key.length, 96)
    assert.ok(/^[0-9a-f]+$/.test(key))
  })

  it('returns different values on each call', () => {
    const a = launcher.generateSecretKey()
    const b = launcher.generateSecretKey()
    assert.notStrictEqual(a, b)
  })
})

describe('getEnv', () => {
  it('includes default UDR variables', () => {
    const env = launcher.getEnv(8199)
    assert.strictEqual(env.UDR_PORT, '8199')
    assert.strictEqual(env.UDR_HOST, '127.0.0.1')
    assert.strictEqual(env.UDR_DESKTOP, 'true')
    assert.strictEqual(env.UDR_STANDALONE, 'true')
    assert.strictEqual(env.ENABLE_AUTH, 'true')
    assert.strictEqual(env.PYTHONUNBUFFERED, '1')
    assert.ok(env.SECRET_KEY)
  })

  it('injects extra env vars', () => {
    const env = launcher.getEnv(8199, { FOO: 'bar', CUSTOM: 'val' })
    assert.strictEqual(env.FOO, 'bar')
    assert.strictEqual(env.CUSTOM, 'val')
  })

  it('includes UDR_STANDALONE and ENABLE_AUTH', () => {
    const env = launcher.getEnv(8199)
    assert.strictEqual(env.UDR_STANDALONE, 'true')
    assert.strictEqual(env.ENABLE_AUTH, 'true')
  })

  it('uses existing SECRET_KEY from process.env', () => {
    process.env.SECRET_KEY = 'my-preshared-key'
    const env = launcher.getEnv(8199)
    assert.strictEqual(env.SECRET_KEY, 'my-preshared-key')
    delete process.env.SECRET_KEY
  })
})

describe('waitForServer', () => {
  it('resolves when server responds', async () => {
    const server = http.createServer((req, res) => res.end('ok'))
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
    const { port } = server.address()
    await launcher.waitForServer(`http://127.0.0.1:${port}`, 5)
    server.close()
  })

  it('rejects when backend crashes', async () => {
    await assert.rejects(
      launcher.waitForServer('http://127.0.0.1:1', 3, () => true),
      { message: 'Backend process crashed' }
    )
  })

  it('rejects after maxRetries', { timeout: 5000 }, async () => {
    await assert.rejects(
      launcher.waitForServer('http://127.0.0.1:1', 3),
      { message: 'Server did not start in time' }
    )
  })
})

describe('spawnBackend', () => {
  it('spawns a process and resolves on matching output', async () => {
    const port = await launcher.findFreePort()
    const result = await launcher.spawnBackend(
      process.execPath,
      [serverScript],
      port,
      tmpDir
    )
    assert.ok(result.process)
    assert.strictEqual(typeof result.crashed, 'function')
    assert.strictEqual(result.crashed(), false)
    result.process.kill()
  })

  it('resolves with crashed flag false when process starts', async () => {
    const port = await launcher.findFreePort()
    const result = await launcher.spawnBackend(
      process.execPath,
      [startupScript],
      port,
      tmpDir
    )
    assert.strictEqual(result.crashed(), false)
    result.process.kill()
  })

  it('rejects when process exits early', async () => {
    const port = await launcher.findFreePort()
    await assert.rejects(
      launcher.spawnBackend(
        process.execPath,
        [exitScript],
        port,
        tmpDir
      ),
      /Backend exited unexpectedly/
    )
  })

  it('rejects on spawn error for invalid command', async () => {
    await assert.rejects(
      launcher.spawnBackend(
        '/nonexistent/binary',
        [],
        8202,
        __dirname
      ),
      /ENOENT/
    )
  })
})

describe('getPlatformHint', () => {
  it('shows macOS hint on Mac', () => {
    const hints = launcher.getPlatformHint(true, false)
    assert.ok(hints.includes('macOS'))
  })

  it('shows Linux hint on non-Mac, non-Win', () => {
    const hints = launcher.getPlatformHint(false, false)
    assert.ok(hints.includes('chmod'))
  })

  it('shows Windows hint on Win', () => {
    const hints = launcher.getPlatformHint(false, true)
    assert.ok(hints.includes('antivirus'))
  })

  it('returns hints for any platform', () => {
    const hints = launcher.getPlatformHint(false, false)
    assert.ok(hints.length > 0)
  })
})
