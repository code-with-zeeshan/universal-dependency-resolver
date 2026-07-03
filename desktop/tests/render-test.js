const { app, BrowserWindow } = require('electron')
const path = require('path')
const fs = require('fs')

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
    await new Promise(r => setTimeout(r, 3000))

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

    const hasStatusDot = await win.webContents.executeJavaScript(
      '!!document.getElementById("statusDot")'
    )
    if (!hasStatusDot) {
      console.error('FAIL: statusDot element not found')
      app.exit(1)
      return
    }
    console.log('PASS: statusDot element found')

    const hasNav = await win.webContents.executeJavaScript(
      '!!document.getElementById("tabNav")'
    )
    if (!hasNav) {
      console.error('FAIL: navigation element not found')
      app.exit(1)
      return
    }
    console.log('PASS: navigation element found')

    console.log('All render tests PASSED')
    app.exit(0)
  } catch (err) {
    console.error('FAIL:', err.message)
    app.exit(1)
  }
})
