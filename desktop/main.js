const { app, BrowserWindow, dialog, ipcMain } = require('electron')
const path = require('path')
const fs = require('fs')
const { spawn } = require('child_process')
const http = require('http')
const net = require('net')

let mainWindow = null
let backendProcess = null
let backendPort = 8199

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

function findBackendCommand() {
  // Priority 1: bundled standalone binary (PyInstaller)
  const binDir = isDev
    ? path.join(__dirname, '..', 'backend', 'dist')
    : path.join(process.resourcesPath, 'backend-bin')
  const binName = isWin ? 'udr-backend.exe' : 'udr-backend'
  const binPath = path.join(binDir, binName)
  if (fs.existsSync(binPath)) {
    return { cmd: binPath, args: [] }
  }

  // Priority 2: bundled venv
  const venvPython = isDev
    ? path.join(__dirname, '..', 'venv', isWin ? 'Scripts' : 'bin', isWin ? 'python.exe' : 'python3')
    : path.join(process.resourcesPath, 'venv', isWin ? 'Scripts' : 'bin', isWin ? 'python.exe' : 'python3')
  if (fs.existsSync(venvPython)) {
    return { cmd: venvPython, args: ['-m', 'uvicorn', 'backend.api.main:app'] }
  }

  // Priority 3: system Python
  const pythonName = isWin ? 'python' : 'python3'
  return { cmd: pythonName, args: ['-m', 'uvicorn', 'backend.api.main:app'] }
}

function startBackend(port) {
  return new Promise((resolve, reject) => {
    const { cmd, args: extraArgs } = findBackendCommand()

    const args = extraArgs.length > 0
      ? [...extraArgs, '--host', '127.0.0.1', '--port', String(port), '--log-level', 'info']
      : [String(port)]

    backendProcess = spawn(cmd, args, {
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

    backendProcess.stdout.on('data', (data) => {
      const msg = data.toString()
      console.log('[backend]', msg)
      if (msg.includes('Uvicorn running') || msg.includes('Application startup complete') || msg.includes('Uvicorn')) {
        resolve()
      }
    })

    backendProcess.stderr.on('data', (data) => {
      console.error('[backend]', data.toString())
    })

    backendProcess.on('error', (err) => {
      console.error('[backend] spawn error:', err.message)
      reject(err)
    })
    backendProcess.on('exit', (code) => {
      console.log(`Backend exited with code ${code}`)
    })

    // Timeout: resolve anyway after 15s
    setTimeout(() => resolve(), 15000)
  })
}

function waitForServer(url, maxRetries = 30) {
  return new Promise((resolve, reject) => {
    let retries = 0
    const check = () => {
      http.get(url, (res) => {
        resolve()
      }).on('error', () => {
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

  // Load frontend FIRST so user sees UI immediately (backend starts in background)
  if (isDev) {
    mainWindow.loadURL('http://localhost:8080')
    mainWindow.webContents.openDevTools()
  } else {
    const distPath = path.join(process.resourcesPath, 'frontend', 'dist', 'index.html')
    mainWindow.loadFile(distPath)
  }

  // Inject backend URL into renderer via preload
  mainWindow.webContents.on('did-finish-load', () => {
    mainWindow.webContents.executeJavaScript(`window.__UDR_BACKEND_URL__ = '${backendUrl}';`)
  })

  // Start backend in background
  try {
    console.log(`Starting backend on port ${backendPort}...`)
    await startBackend(backendPort)
    console.log('Backend started, waiting for server...')
    await waitForServer(`${backendUrl}/api/v1/docs`)
    console.log('Backend ready!')
    mainWindow.webContents.executeJavaScript('window.__UDR_BACKEND_READY__ = true')
  } catch (e) {
    console.error('Backend start warning:', e.message)
    dialog.showErrorBox(
      'Backend Failed to Start',
      `The backend server could not be started.\n\n${e.message}\n\nMake sure Python 3.11+ is installed on your system. If Python is already installed, try reinstalling this application.`
    )
  }

  mainWindow.on('closed', () => {
    mainWindow = null
  })
}

// IPC handlers
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
