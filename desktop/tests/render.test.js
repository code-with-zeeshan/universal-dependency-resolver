const { describe, it } = require('node:test')
const assert = require('node:assert')
const path = require('path')
const fs = require('fs')
const { spawnSync } = require('child_process')

const xvfbAvailable = (() => {
  try { return spawnSync('which', ['xvfb-run'], { stdio: 'pipe' }).status === 0 } catch { return false }
})()

const electronBin = path.join(__dirname, '..', 'node_modules', '.bin', 'electron')

describe('Electron render test', { skip: !xvfbAvailable && !process.env.DISPLAY }, () => {
  it('renders the desktop window and captures screenshot', () => {
    const testScript = path.join(__dirname, 'render-test.js')

    let cmd, args
    if (xvfbAvailable && !process.env.DISPLAY) {
      cmd = 'xvfb-run'
      args = ['--auto-servernum', electronBin, testScript]
    } else {
      cmd = electronBin
      args = [testScript]
    }

    const result = spawnSync(cmd, args, {
      cwd: path.join(__dirname, '..'),
      timeout: 30000,
      stdio: 'pipe',
      env: { ...process.env, ELECTRON_ENABLE_STACK_DUMPING: 'false' },
    })

    const stdout = result.stdout.toString()
    const stderr = result.stderr.toString()
    for (const line of stdout.split('\n').filter(Boolean)) console.log(line)
    for (const line of stderr.split('\n').filter(Boolean)) console.log(line)

    const screenshotPath = '/tmp/udr-render-test.png'
    if (fs.existsSync(screenshotPath)) {
      const stat = fs.statSync(screenshotPath)
      assert.ok(stat.size > 1000, `Screenshot too small: ${stat.size} bytes`)
    }

    assert.strictEqual(result.status, 0, `Exit code ${result.status}\n${stdout}\n${stderr}`)
  })
})
