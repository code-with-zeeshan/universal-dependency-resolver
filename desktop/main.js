const { app, BrowserWindow, dialog, ipcMain } = require('electron')
const path = require('path')
const fs = require('fs')
const { spawn } = require('child_process')
const http = require('http')
const net = require('net')

let mainWindow = null
let backendProcess = null
let backendPort = 8199
let backendCrashed = false

const isDev = !app.isPackaged
const isWin = process.platform === 'win32'
const backendDir = isDev
  ? path.join(__dirname, '..', 'backend')
  : path.join(process.resourcesPath, 'backend')

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

function getFallbackCommands() {
  const cmds = []
  const binDir = isDev
    ? path.join(__dirname, '..', 'backend', 'dist')
    : path.join(process.resourcesPath, 'backend-bin')
  const binName = isWin ? 'udr-backend.exe' : 'udr-backend'
  const binPath = path.join(binDir, binName)
  if (fs.existsSync(binPath)) {
    cmds.push({ cmd: binPath, args: [] })
  }
  const pythonName = isWin ? 'python' : 'python3'
  cmds.push({ cmd: pythonName, args: ['-m', 'uvicorn', 'backend.api.main:app'] })
  return cmds
}

function spawnBackend(cmd, args, port) {
  return new Promise((resolve, reject) => {
    backendCrashed = false

    const allArgs = args.length > 0
      ? [...args, '--host', '127.0.0.1', '--port', String(port), '--log-level', 'info']
      : [String(port)]

    backendProcess = spawn(cmd, allArgs, {
      cwd: backendDir,
      env: {
        ...process.env,
        UDR_PORT: String(port),
        UDR_HOST: '127.0.0.1',
        UDR_DESKTOP: 'true',
        PYTHONUNBUFFERED: '1',
      },
      stdio: ['ignore', 'pipe', 'pipe'],
    })

    let started = false

    function onOutput(data) {
      const msg = data.toString()
      if (!started && (msg.includes('Uvicorn running') || msg.includes('Application startup complete') || msg.includes('Uvicorn'))) {
        started = true
        resolve()
      }
    }

    backendProcess.stdout.on('data', (data) => {
      console.log('[backend:out]', data.toString().trimEnd())
      onOutput(data)
    })

    backendProcess.stderr.on('data', (data) => {
      const msg = data.toString()
      console.log('[backend:err]', msg.trimEnd())
      onOutput(data)
    })

    backendProcess.on('error', (err) => {
      console.error('[backend] spawn error:', err.message)
      backendCrashed = true
      if (!started) reject(err)
    })

    backendProcess.on('exit', (code) => {
      console.log(`Backend exited with code ${code}`)
      backendCrashed = true
      if (!started) reject(new Error(`Backend exited unexpectedly with code ${code}`))
    })

    setTimeout(() => {
      if (!started) resolve()
    }, 15000)
  })
}

function waitForServer(url, maxRetries = 30) {
  return new Promise((resolve, reject) => {
    let retries = 0
    const check = () => {
      if (backendCrashed) {
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

async function startBackendWithFallback(port) {
  const fallbacks = getFallbackCommands()
  let lastError = null
  for (const fb of fallbacks) {
    try {
      console.log(`[backend] Trying: ${fb.cmd}`)
      await spawnBackend(fb.cmd, fb.args, port)
      console.log('[backend] Spawn succeeded, waiting for HTTP...')
      await waitForServer(`http://127.0.0.1:${port}/api/v1/docs`)
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
  backendPort = await findFreePort()
  const backendUrl = `http://127.0.0.1:${backendPort}`

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
  } catch (e) {
    console.error('Backend start failed:', e.message)
    let msg = `The backend server could not be started.\n\n${e.message}`
    if (e.message.includes('exited unexpectedly') || e.message.includes('crashed')) {
      msg += '\n\nIf using the packaged app, the bundled backend binary may be blocked by antivirus or missing system libraries. Try running the Python backend directly:\n  python3 -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8199'
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