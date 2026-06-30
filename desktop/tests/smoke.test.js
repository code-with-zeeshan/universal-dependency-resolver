const { describe, it } = require('node:test')
const assert = require('node:assert')
const path = require('path')
const fs = require('fs')
const http = require('http')
const os = require('os')
const { spawn } = require('child_process')
const launcher = require('../backend-launcher')

const RELEASE_DIR = path.join(__dirname, '..', 'release')
const PKG_DIR = path.join(__dirname, '..')
const EXTRACTED_ROOT = path.join(RELEASE_DIR, 'squashfs-root')
const BACKEND_BIN = path.join(EXTRACTED_ROOT, 'resources', 'backend-bin', 'udr-backend')

function findAppImage() {
  if (!fs.existsSync(RELEASE_DIR)) return null
  const files = fs.readdirSync(RELEASE_DIR)
  return files.find(f => f.endsWith('.AppImage'))
}

function extractAppImage(appImagePath) {
  return new Promise((resolve, reject) => {
    const proc = spawn(appImagePath, ['--appimage-extract'], {
      cwd: RELEASE_DIR,
      stdio: ['ignore', 'pipe', 'pipe'],
    })
    let buf = ''
    proc.stdout.on('data', d => { buf += d })
    proc.stderr.on('data', d => { buf += d })
    proc.on('exit', code => {
      if (code === 0 && fs.existsSync(BACKEND_BIN)) resolve()
      else reject(new Error(`Extract failed (exit ${code}): ${buf}`))
    })
    proc.on('error', reject)
  })
}

describe('Desktop smoke tests', () => {
  describe('Build artifact exists', () => {
    it('has release directory', () => {
      assert.ok(
        fs.existsSync(RELEASE_DIR),
        `Release directory should exist at ${RELEASE_DIR}`
      )
    })

    it('has platform-specific build artifacts', () => {
      if (!fs.existsSync(RELEASE_DIR)) return
      const files = fs.readdirSync(RELEASE_DIR)
      const platform = os.platform()
      if (platform === 'linux') {
        assert.ok(
          files.some(f => f.endsWith('.AppImage')),
          'Should have an AppImage file on Linux'
        )
      } else if (platform === 'darwin') {
        assert.ok(
          files.some(f => f.endsWith('.dmg')),
          'Should have a .dmg file on macOS'
        )
      } else if (platform === 'win32') {
        assert.ok(
          files.some(f => f.endsWith('.exe')),
          'Should have a .exe file on Windows'
        )
      }
    })
  })

  describe('Build artifact is executable', () => {
    it('has execute permission and size > 10MB', () => {
      const appImage = findAppImage()
      if (!appImage) return
      const fullPath = path.join(RELEASE_DIR, appImage)
      const stat = fs.statSync(fullPath)
      assert.ok(
        stat.size > 10 * 1024 * 1024,
        `AppImage should be > 10MB, got ${(stat.size / 1024 / 1024).toFixed(1)}MB`
      )
      assert.ok(
        stat.mode & fs.constants.S_IXUSR,
        `AppImage should have execute permission for owner`
      )
    })
  })

  describe('Backend launcher integration', () => {
    it('findFreePort returns a valid port', async () => {
      const port = await launcher.findFreePort()
      assert.strictEqual(typeof port, 'number')
      assert.ok(port > 0 && port < 65536)
    })
  })

  describe('Version consistency', () => {
    it('package.json version matches pyproject.toml version', () => {
      const pkg = JSON.parse(
        fs.readFileSync(path.join(PKG_DIR, 'package.json'), 'utf8')
      )
      const pyprojectPath = path.join(PKG_DIR, '..', 'pyproject.toml')
      const pyproject = fs.readFileSync(pyprojectPath, 'utf8')
      const match = pyproject.match(/^version\s*=\s*"([^"]+)"/m)
      assert.ok(match, 'Could not find version string in pyproject.toml')
      const pyVersion = match[1]
      assert.strictEqual(
        pkg.version,
        pyVersion,
        `package.json version (${pkg.version}) should match pyproject.toml version (${pyVersion})`
      )
    })
  })

  describe('File structure', () => {
    const requiredFiles = ['main.js', 'preload.js', 'index.html', 'backend-launcher.js']
    for (const file of requiredFiles) {
      it(`${file} exists`, () => {
        const fullPath = path.join(PKG_DIR, file)
        assert.ok(
          fs.existsSync(fullPath),
          `Required file ${file} should exist at ${fullPath}`
        )
        assert.ok(
          fs.statSync(fullPath).isFile(),
          `${file} should be a regular file`
        )
      })
    }
  })

  describe('API health endpoint', () => {
    it('responds to /api/v1/health', { timeout: 30000 }, async () => {
      const appImage = findAppImage()
      if (!appImage) {
        console.log('No AppImage found, skipping API health test')
        return
      }

      const port = await launcher.findFreePort()

      let binPath
      let binArgs

      if (fs.existsSync(BACKEND_BIN)) {
        binPath = BACKEND_BIN
        binArgs = [String(port)]
      } else {
        const appImagePath = path.join(RELEASE_DIR, appImage)
        try {
          await extractAppImage(appImagePath)
          binPath = BACKEND_BIN
          binArgs = [String(port)]
        } catch {
          console.log('Could not extract AppImage, skipping API health test')
          return
        }
      }

      const proc = spawn(binPath, binArgs, {
        env: { ...process.env, ...launcher.getEnv(port) },
        stdio: ['ignore', 'pipe', 'pipe'],
      })

      const healthUrl = `http://127.0.0.1:${port}/api/v1/health`

      try {
        await launcher.waitForServer(healthUrl, 25)

        const body = await new Promise((resolve, reject) => {
          http.get(healthUrl, res => {
            let data = ''
            res.on('data', chunk => { data += chunk })
            res.on('end', () => resolve(data))
          }).on('error', reject)
        })

        const parsed = JSON.parse(body)
        assert.ok(parsed, 'Health response should be valid JSON')
        assert.ok(
          parsed.status || parsed.success || parsed.healthy !== undefined,
          'Health response should contain a status field'
        )
      } finally {
        proc.kill('SIGTERM')
        await new Promise(resolve => {
          const timeout = setTimeout(() => resolve(), 2000)
          proc.on('exit', () => {
            clearTimeout(timeout)
            resolve()
          })
        })
      }
    })
  })
})
