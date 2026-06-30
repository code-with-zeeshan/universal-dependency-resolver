const { app, BrowserWindow, dialog, ipcMain, Tray, Menu, Notification } = require('electron')
const path = require('path')
const fs = require('fs')
const launcher = require('./backend-launcher')

let mainWindow = null
let backendProcess = null
let backendPort = 8199
let backendCrashed = false
let tray = null
let healthCheckInterval = null
let restarting = false

const isDev = !app.isPackaged
const isWin = process.platform === 'win32'
const isMac = process.platform === 'darwin'
const BACKEND_HOST = process.env.UDR_HOST || '127.0.0.1'
const backendBinDir = isDev
  ? path.join(__dirname, '..', 'backend', 'dist')
  : path.join(process.resourcesPath, 'backend-bin')

const HEALTH_CHECK_INTERVAL_MS = 30000
const HEALTH_CHECK_URL = '/api/v1/health'

// ── Window state persistence ──────────────────────────────────────────
const STATE_FILE = path.join(app.getPath('userData'), 'window-state.json')

function loadWindowState() {
  try {
    if (fs.existsSync(STATE_FILE)) {
      const raw = fs.readFileSync(STATE_FILE, 'utf-8')
      return JSON.parse(raw)
    }
  } catch { /* ignore corrupted state file */ }
  return null
}

function saveWindowState(win) {
  if (!win) return
  try {
    const bounds = win.getBounds()
    const data = JSON.stringify({
      x: bounds.x, y: bounds.y,
      width: bounds.width, height: bounds.height,
      isMaximized: win.isMaximized(),
    })
    const tmp = STATE_FILE + '.tmp'
    fs.writeFileSync(tmp, data, 'utf-8')
    fs.renameSync(tmp, STATE_FILE)
  } catch { /* ignore */ }
}

// ── Env var filtering ────────────────────────────────────────────────
function getFilteredEnv(port) {
  const safeKeys = new Set([
    'PATH', 'HOME', 'USER', 'USERNAME', 'TEMP', 'TMP', 'TMPDIR',
    'LANG', 'LC_ALL', 'SHELL', 'PWD', 'PYTHONUNBUFFERED', 'VIRTUAL_ENV',
    'CONDA_PREFIX', 'CONDA_DEFAULT_ENV',
    'LD_LIBRARY_PATH', 'LD_PRELOAD', 'DYLD_LIBRARY_PATH',
    'DISPLAY', 'WAYLAND_DISPLAY', 'DBUS_SESSION_BUS_ADDRESS',
    'XDG_CURRENT_DESKTOP', 'XDG_SESSION_TYPE', 'XDG_RUNTIME_DIR',
    'XDG_CONFIG_DIRS', 'XDG_DATA_DIRS',
  ])
  const filtered = {}
  for (const key of safeKeys) {
    if (process.env[key] !== undefined) filtered[key] = process.env[key]
  }
  return launcher.getEnv(port, filtered)
}

// ── Single-instance lock ──────────────────────────────────────────────
const gotLock = app.requestSingleInstanceLock()
if (!gotLock) {
  app.quit()
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore()
      mainWindow.show()
      mainWindow.focus()
    }
  })
}

// ── Backend restart logic ─────────────────────────────────────────────
async function restartBackend() {
  if (restarting) return
  restarting = true
  try {
    console.log('[backend] Attempting restart...')
    killBackend()
    backendCrashed = false
    const newPort = await launcher.findFreePort()
    backendPort = newPort
    try {
      await startBackendWithFallback(newPort)
      console.log('[backend] Restart successful')
      if (mainWindow) {
        mainWindow.webContents.send('backend-ready')
        mainWindow.webContents.executeJavaScript(`window.__UDR_BACKEND_URL__ = 'http://${BACKEND_HOST}:${newPort}';`)
        mainWindow.webContents.executeJavaScript("document.title = 'UDR'")
      }
      startHealthCheck()
    } catch (e) {
      console.error('[backend] Restart failed:', e.message)
    }
  } finally {
    restarting = false
  }
}

function startHealthCheck() {
  stopHealthCheck()
  healthCheckInterval = setInterval(async () => {
    if (restarting) return
    try {
      await launcher.httpGet(`http://${BACKEND_HOST}:${backendPort}${HEALTH_CHECK_URL}`)
      if (mainWindow) {
        mainWindow.webContents.executeJavaScript("document.title = 'UDR'")
      }
    } catch {
      console.warn('[backend] Health check failed, attempting restart...')
      if (mainWindow) {
        mainWindow.webContents.executeJavaScript("document.title = 'UDR - Backend reconnecting...'")
      }
      await restartBackend()
    }
  }, HEALTH_CHECK_INTERVAL_MS)
}

function stopHealthCheck() {
  if (healthCheckInterval) {
    clearInterval(healthCheckInterval)
    healthCheckInterval = null
  }
}

// ── Fallback commands ─────────────────────────────────────────────────
function getFallbackCommands() {
  const cmds = []
  const binName = isWin ? 'udr-backend.exe' : 'udr-backend'
  const binPath = path.join(backendBinDir, binName)
  if (fs.existsSync(binPath)) {
    cmds.push({ cmd: binPath, args: [], isBinary: true })
  }
  if (isDev) {
    const pythonName = isWin ? 'python' : 'python3'
    cmds.push({ cmd: pythonName, args: ['-m', 'backend.cli', 'serve', '--mode', 'local'], isBinary: false })
  } else {
    cmds.push({ cmd: 'udr', args: ['serve'], isBinary: false })
    const pythonName = isWin ? 'python' : 'python3'
    cmds.push({ cmd: pythonName, args: ['-m', 'backend.cli', 'serve', '--mode', 'local'], isBinary: false })
  }
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
      console.log(`[backend] Trying: ${fb.cmd} ${fb.args.join(' ')}`)
      const cwd = fb.isBinary ? backendBinDir : (isDev ? path.join(__dirname, '..') : app.getPath('home'))
      const env = getFilteredEnv(port)
      const result = await launcher.spawnBackend(fb.cmd, fb.args, port, cwd, env)
      backendProcess = result.process
      backendCrashed = false
      const crashedCheck = result.crashed

      console.log('[backend] Spawn succeeded, waiting for HTTP...')
      await launcher.waitForServer(`http://${BACKEND_HOST}:${port}/api/v1/health`, 120, () => {
        if (crashedCheck()) return true
        return backendCrashed
      })
      console.log('[backend] Server ready!')
      return
    } catch (err) {
      lastError = err
      console.warn(`[backend] ${fb.cmd} failed: ${err.message}`)
      if (backendProcess) {
        killBackend()
      }
    }
  }
  throw lastError || new Error('All backend attempts failed')
}

async function createWindow() {
  backendPort = await launcher.findFreePort()
  const backendUrl = `http://${BACKEND_HOST}:${backendPort}`

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

  const savedState = loadWindowState()
  const winOptions = {
    width: savedState ? savedState.width : 1280,
    height: savedState ? savedState.height : 860,
    minWidth: 900,
    minHeight: 600,
    title: 'UDR - Starting...',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  }
  if (savedState && savedState.x !== undefined && savedState.y !== undefined) {
    winOptions.x = savedState.x
    winOptions.y = savedState.y
  }

  mainWindow = new BrowserWindow(winOptions)

  if (savedState && savedState.isMaximized) {
    mainWindow.maximize()
  }

  if (isDev) {
    mainWindow.loadFile(path.join(__dirname, 'index.html'))
    mainWindow.webContents.openDevTools()
  } else {
    mainWindow.loadFile(path.join(__dirname, 'index.html'))
  }

  mainWindow.webContents.on('did-finish-load', () => {
    mainWindow.webContents.executeJavaScript(`window.__UDR_BACKEND_URL__ = '${backendUrl}';`)
  })

  mainWindow.webContents.executeJavaScript(
    `console.log('UDR Desktop: starting backend on port ${backendPort}...')`
  )

  try {
    console.log(`Starting backend on port ${backendPort}...`)
    mainWindow.webContents.executeJavaScript("document.title = 'UDR - Starting backend...'")
    await startBackendWithFallback(backendPort)
    mainWindow.webContents.executeJavaScript('window.__UDR_BACKEND_READY__ = true')
    createTray()
    if (Notification.isSupported()) {
      new Notification({ title: 'UDR', body: 'Backend started successfully' })
    }
    mainWindow.webContents.send('backend-ready')
    startHealthCheck()
  } catch (e) {
    console.error('Backend start failed:', e.message)
    let msg = `The backend server could not be started.\n\n${e.message}${launcher.getPlatformHint(isMac, isWin)}`
    msg += '\n\nIf this problem persists, install the Python package:\n  pip install ud-resolver\nThen run: udr serve\n\nOr try reinstalling the desktop app.'
    dialog.showErrorBox('Backend Failed to Start', msg)
  }

  // Window state persistence on resize/move
  let saveTimer = null
  const debouncedSave = () => {
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => saveWindowState(mainWindow), 500)
  }
  mainWindow.on('resize', debouncedSave)
  mainWindow.on('move', debouncedSave)
  mainWindow.on('maximize', debouncedSave)
  mainWindow.on('unmaximize', debouncedSave)

  // On close, actually quit (so NSIS installer can overwrite files)
  mainWindow.on('close', () => {
    app.isQuitting = true
  })

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
  return `http://${BACKEND_HOST}:${backendPort}`
})

function createTray() {
  try {
    const iconPath = path.join(__dirname, 'assets', 'tray-icon.png')
    if (!fs.existsSync(iconPath)) return
    tray = new Tray(iconPath)
    const contextMenu = Menu.buildFromTemplate([
      { label: 'Show UDR', click: () => { if (mainWindow) { mainWindow.show(); mainWindow.focus() } } },
      { type: 'separator' },
      { label: 'Quit', click: () => { app.isQuitting = true; app.quit() } },
    ])
    tray.setToolTip('Universal Dependency Resolver')
    tray.setContextMenu(contextMenu)
    tray.on('click', () => { if (mainWindow) { mainWindow.show(); mainWindow.focus() } })
  } catch (e) {
    console.warn('Tray creation failed:', e.message)
  }
}

function createMenu() {
  const isMac = process.platform === 'darwin'
  const template = [
    {
      label: 'File',
      submenu: [
        {
          label: 'Reload Frontend',
          accelerator: 'CmdOrCtrl+R',
          click: (item, focusedWindow) => {
            if (focusedWindow) focusedWindow.webContents.reload()
          },
        },
        {
          label: 'Restart Backend',
          accelerator: 'CmdOrCtrl+Shift+R',
          click: async () => {
            await restartBackend()
          },
        },
        { type: 'separator' },
        isMac ? { role: 'close', label: 'Quit' } : { role: 'quit', label: 'Quit' },
      ],
    },
    {
      label: 'Help',
      submenu: [
        {
          label: 'About UDR',
          click: () => {
            dialog.showMessageBox(mainWindow, {
              type: 'info',
              title: 'About UDR',
              message: 'Universal Dependency Resolver',
              detail: `Version ${app.getVersion()}\nElectron ${process.versions.electron}\nNode.js ${process.versions.node}\n\nCross-ecosystem dependency resolver for PyPI, npm, Cargo, Conda, Maven, and more.`,
            })
          },
        },
        { type: 'separator' },
        {
          label: 'Toggle Developer Tools',
          accelerator: isMac ? 'Alt+Cmd+I' : 'Ctrl+Shift+I',
          click: (item, focusedWindow) => {
            if (focusedWindow) focusedWindow.webContents.toggleDevTools()
          },
        },
      ],
    },
  ]

  const menu = Menu.buildFromTemplate(template)
  Menu.setApplicationMenu(menu)
}

app.whenReady().then(() => {
  if (gotLock) {
    createMenu()
    createWindow()
  }
})

function killBackend() {
  if (!backendProcess) return
  try {
    if (isWin) {
      const { execSync } = require('child_process')
      execSync(`taskkill /pid ${backendProcess.pid} /T /F`, { stdio: 'ignore' })
    } else {
      backendProcess.kill('SIGTERM')
      const pid = backendProcess.pid
      setTimeout(() => {
        try { process.kill(pid, 'SIGKILL') } catch { /* already dead */ }
      }, 3000)
    }
  } catch { /* ignore */ }
  backendProcess = null
}

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

app.on('activate', () => {
  if (mainWindow === null && backendProcess) {
    createWindow()
  } else if (mainWindow === null) {
    createWindow()
  } else {
    mainWindow.show()
    mainWindow.focus()
  }
})

app.on('before-quit', () => {
  stopHealthCheck()
  killBackend()
})

app.on('will-quit', () => {
  stopHealthCheck()
  killBackend()
})
