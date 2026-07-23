const { app, BrowserWindow, ipcMain } = require('electron')
const path = require('path')
const fs = require('fs')

// Register handlers that app.js depends on, so IPC calls don't fail
ipcMain.handle('get-backend-url', () => 'http://127.0.0.1:8199')

async function waitForElement(win, js, label, timeoutMs = 20000) {
  const deadline = Date.now() + timeoutMs
  let lastErr
  while (Date.now() < deadline) {
    try {
      const result = await win.webContents.executeJavaScript(js)
      if (result) return result
    } catch (err) {
      lastErr = err
    }
    await new Promise(r => setTimeout(r, 300))
  }
  throw lastErr || new Error(`Timed out waiting for ${label}`)
}

app.whenReady().then(async () => {
  const win = new BrowserWindow({
    width: 1280,
    height: 860,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      preload: path.join(__dirname, '..', 'preload.js'),
    },
  })

  try {
    await win.loadFile(path.join(__dirname, '..', 'index.html'))

    // Wait for static DOM elements to be present (instead of fixed timeout)
    await waitForElement(win, '!!document.getElementById("statusDot")', 'statusDot')
    await waitForElement(win, '!!document.getElementById("tabNav")', 'tabNav')
    console.log('PASS: DOM elements found')

    // Give page JS a moment to render
    await new Promise(r => setTimeout(r, 1000))

    const image = await win.capturePage()
    const screenshotPath = '/tmp/udr-render-test.png'
    fs.writeFileSync(screenshotPath, image.toPNG())

    const stat = fs.statSync(screenshotPath)
    if (stat.size < 1000) {
      console.error(`FAIL: Screenshot too small (${stat.size} bytes)`)
      app.exit(1)
      return
    }
    console.log(`PASS: Screenshot ${stat.size} bytes`)

    const title = await win.webContents.executeJavaScript('document.title')
    if (!title || !title.includes('UDR')) {
      console.error(`FAIL: Title does not contain UDR: "${title}"`)
      app.exit(1)
      return
    }
    console.log(`PASS: Title="${title}"`)

    console.log('All render tests PASSED')
    app.exit(0)
  } catch (err) {
    console.error('FAIL:', err.message)
    app.exit(1)
  }
})
