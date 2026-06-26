const { app, BrowserWindow, dialog, ipcMain, Tray, Menu, Notification } = require('electron')
const path = require('path')
const fs = require('fs')
const launcher = require('./backend-launcher')

let mainWindow = null
let backendProcess = null
let backendPort = 8199
let backendCrashed = false
let tray = null

const isDev = !app.isPackaged
const isWin = process.platform === 'win32'
const isMac = process.platform === 'darwin'
const backendDir = isDev
  ? path.join(__dirname, '..', 'backend')
  : path.join(process.resourcesPath, 'backend')
const backendParentDir = path.dirname(backendDir)

function getFallbackCommands() {
  const cmds = []
  const binDir = isDev
    ? path.join(__dirname, '..', 'backend', 'dist')
    : path.join(process.resourcesPath, 'backend-bin')
  const binName = isWin ? 'udr-backend.exe' : 'udr-backend'
  const binPath = path.join(binDir, binName)
  if (fs.existsSync(binPath)) {
    cmds.push({ cmd: binPath, args: [], isBinary: true })
  }
  const pythonName = isWin ? 'python' : 'python3'
  cmds.push({ cmd: pythonName, args: ['-m', 'uvicorn', 'backend.api.main:app'], isBinary: false })
  return cmds
}

function envForPort(port) {
  return launcher.getEnv(port)
}

async function startBackendWithFallback(port) {
  const fallbacks = getFallbackCommands()
  let lastError = null
  for (const fb of fallbacks) {
    try {
      console.log(`[backend] Trying: ${fb.cmd}`)
      const cwd = fb.isBinary ? backendDir : backendParentDir
      const result = await launcher.spawnBackend(fb.cmd, fb.args, port, fb.isBinary, cwd)
      backendProcess = result.process
      backendCrashed = false
      const crashedCheck = result.crashed

      console.log('[backend] Spawn succeeded, waiting for HTTP...')
      await launcher.waitForServer(`http://127.0.0.1:${port}/api/v1/docs`, 30, () => {
        if (crashedCheck()) return true
        return backendCrashed
      })
      console.log('[backend] Server ready!')
      return
    } catch (err) {
      lastError = err
      console.warn(`[backend] ${fb.cmd} failed: ${err.message}`)
      if (backendProcess) {
        backendProcess.kill()
        backendProcess = null
      }
    }
  }
  throw lastError || new Error('All backend attempts failed')
}

async function createWindow() {
  backendPort = await launcher.findFreePort()
  const backendUrl = `http://127.0.0.1:${backendPort}`

  // Auto-update (only in production)
  if (!isDev) {
    try {
      const { autoUpdater } = require('electron-updater')
      autoUpdater.checkForUpdatesAndNotify()
      autoUpdater.on('update-downloaded', () => {
        if (Notification.isSupported()) {
          new Notification({
            title: 'UDR Update',
            body: 'A new version has been downloaded. Restart to apply.',
          })
        }
        const { dialog: d } = require('electron')
        d.showMessageBox(mainWindow, {
          type: 'info',
          title: 'Update Ready',
          message: 'A new version has been downloaded. Restart now to apply the update?',
          buttons: ['Restart', 'Later'],
        }).then(({ response }) => {
          if (response === 0) autoUpdater.quitAndInstall()
        })
      })
    } catch (e) {
      console.warn('Auto-updater not available:', e.message)
    }
  }

  mainWindow = new BrowserWindow({
    width: 1280,
    height: 860,
    minWidth: 900,
    minHeight: 600,
    title: 'Universal Dependency Resolver',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  if (isDev) {
    mainWindow.loadURL('http://localhost:8080')
    mainWindow.webContents.openDevTools()
  } else {
    const distPath = path.join(process.resourcesPath, 'frontend', 'dist', 'index.html')
    mainWindow.loadFile(distPath)
  }

  mainWindow.webContents.on('did-finish-load', () => {
    mainWindow.webContents.executeJavaScript(`window.__UDR_BACKEND_URL__ = '${backendUrl}';`)
  })

  try {
    console.log(`Starting backend on port ${backendPort}...`)
    await startBackendWithFallback(backendPort)
    mainWindow.webContents.executeJavaScript('window.__UDR_BACKEND_READY__ = true')
    createTray()
    if (Notification.isSupported()) {
      new Notification({ title: 'UDR', body: 'Backend started successfully' })
    }
  } catch (e) {
    console.error('Backend start failed:', e.message)
    let msg = `The backend server could not be started.\n\n${e.message}${launcher.getPlatformHint(isMac, isWin)}`
    if (e.message.includes('exited unexpectedly') || e.message.includes('crashed')) {
      msg += '\n\nThe bundled backend binary may be blocked by antivirus or missing system libraries. Try running the Python backend manually:\n  python3 -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8199'
    }
    msg += '\n\nMake sure Python 3.11+ is installed. If Python is already installed, try running the backend manually.'
    dialog.showErrorBox('Backend Failed to Start', msg)
  }

  mainWindow.on('closed', () => {
    mainWindow = null
  })
}

ipcMain.handle('select-directory', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory'],
    title: 'Select Project Directory',
  })
  if (result.canceled) return null
  return result.filePaths[0]
})

ipcMain.handle('get-backend-url', () => {
  return `http://127.0.0.1:${backendPort}`
})

function createTray() {
  try {
    const iconPath = path.join(__dirname, 'assets', 'tray-icon.png')
    if (!fs.existsSync(iconPath)) return
    tray = new Tray(iconPath)
    const contextMenu = Menu.buildFromTemplate([
      { label: 'Show UDR', click: () => mainWindow && mainWindow.show() },
      { type: 'separator' },
      { label: 'Quit', click: () => { app.isQuitting = true; app.quit() } },
    ])
    tray.setToolTip('Universal Dependency Resolver')
    tray.setContextMenu(contextMenu)
    tray.on('click', () => mainWindow && mainWindow.show())
  } catch (e) {
    console.warn('Tray creation failed:', e.message)
  }
}

app.whenReady().then(createWindow)

app.on('window-all-closed', () => {
  if (backendProcess) {
    backendProcess.kill()
    backendProcess = null
  }
  if (process.platform !== 'darwin') app.quit()
})

app.on('activate', () => {
  if (mainWindow === null) createWindow()
})

app.on('before-quit', () => {
  if (backendProcess) {
    backendProcess.kill()
    backendProcess = null
  }
})
