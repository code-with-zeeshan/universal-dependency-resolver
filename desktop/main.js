const { app, BrowserWindow, dialog, ipcMain } = require('electron')
const path = require('path')
const { spawn } = require('child_process')
const http = require('http')
const net = require('net')

let mainWindow = null
let backendProcess = null
let backendPort = 8199

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

function startBackend(port) {
  return new Promise((resolve, reject) => {
    const isDev = !app.isPackaged
    const backendDir = isDev
      ? path.join(__dirname, '..', 'backend')
      : path.join(process.resourcesPath, 'backend')

    const isWin = process.platform === 'win32'
    const pythonBin = isWin ? 'python.exe' : 'python3'
    const venvPython = isDev
      ? path.join(__dirname, '..', 'venv', isWin ? 'Scripts' : 'bin', pythonBin)
      : path.join(process.resourcesPath, 'venv', isWin ? 'Scripts' : 'bin', pythonBin)

    const pythonCmd = require('fs').existsSync(venvPython) ? venvPython : (isWin ? 'python' : 'python3')

    backendProcess = spawn(pythonCmd, [
      '-m', 'uvicorn', 'backend.api.main:app',
      '--host', '127.0.0.1',
      '--port', String(port),
      '--log-level', 'info',
    ], {
      cwd: backendDir,
      env: {
        ...process.env,
        UDR_PORT: String(port),
        UDR_DESKTOP: 'true',
        PYTHONUNBUFFERED: '1',
      },
      stdio: ['ignore', 'pipe', 'pipe'],
    })

    backendProcess.stdout.on('data', (data) => {
      const msg = data.toString()
      console.log('[backend]', msg)
      if (msg.includes('Uvicorn running') || msg.includes('Application startup complete')) {
        resolve()
      }
    })

    backendProcess.stderr.on('data', (data) => {
      console.error('[backend]', data.toString())
    })

    backendProcess.on('error', reject)
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

  // Start backend
  try {
    console.log(`Starting backend on port ${backendPort}...`)
    await startBackend(backendPort)
    console.log('Backend started, waiting for server...')
    await waitForServer(`${backendUrl}/api/v1/docs`)
    console.log('Backend ready!')
  } catch (e) {
    console.error('Backend start warning:', e.message)
    dialog.showErrorBox(
      'Backend Failed to Start',
      `The Python backend could not be started.\n\n${e.message}\n\nMake sure Python 3.11+ and uvicorn are installed.`
    )
  }

  // Load frontend
  const isDev = !app.isPackaged
  if (isDev) {
    // Development: use vite dev server
    mainWindow.loadURL('http://localhost:8080')
    mainWindow.webContents.openDevTools()
  } else {
    // Production: serve built files from extraResources
    const distPath = path.join(process.resourcesPath, 'frontend', 'dist', 'index.html')
    mainWindow.loadFile(distPath)
  }

  // Inject backend URL into renderer via preload
  mainWindow.webContents.on('did-finish-load', () => {
    mainWindow.webContents.executeJavaScript(`window.__UDR_BACKEND_URL__ = '${backendUrl}';`)
  })

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
