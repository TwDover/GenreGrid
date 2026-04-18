import { app, BrowserWindow, ipcMain, nativeImage, protocol, net as electronNet } from 'electron'
import { spawn, ChildProcess } from 'child_process'
import nodeNet from 'net'
import path from 'path'
import fs from 'fs'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const RENDERER_DIST = path.join(__dirname, '../dist')
const VITE_DEV_SERVER_URL = process.env.VITE_DEV_SERVER_URL

// Register app:// as a privileged scheme so absolute paths (/samples/...) resolve correctly
// in the packaged app (file:// breaks absolute URL resolution)
protocol.registerSchemesAsPrivileged([
  { scheme: 'app', privileges: { secure: true, standard: true, supportFetchAPI: true } },
])

let backendProcess: ChildProcess | null = null
let backendPort = 8000  // default for dev (user runs backend manually)

// ── Port utilities ──────────────────────────────────────────────────────────

function findFreePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = nodeNet.createServer()
    server.listen(0, '127.0.0.1', () => {
      const port = (server.address() as nodeNet.AddressInfo).port
      server.close(() => resolve(port))
    })
    server.on('error', reject)
  })
}

// Wait until the backend HTTP server is accepting connections
function waitForBackend(port: number, retries = 40, delayMs = 250): Promise<void> {
  return new Promise((resolve, reject) => {
    const attempt = (n: number) => {
      const sock = nodeNet.createConnection({ port, host: '127.0.0.1' })
      sock.on('connect', () => { sock.destroy(); resolve() })
      sock.on('error', () => {
        if (n <= 0) return reject(new Error('Backend did not start in time'))
        setTimeout(() => attempt(n - 1), delayMs)
      })
    }
    attempt(retries)
  })
}

// ── Backend spawning ─────────────────────────────────────────────────────────

async function startBackend(): Promise<void> {
  if (!app.isPackaged) return  // dev: user runs the backend manually

  const exeName = process.platform === 'win32' ? 'genregrid-backend.exe' : 'genregrid-backend'
  const exePath = path.join(process.resourcesPath, 'backend', exeName)

  if (!fs.existsSync(exePath)) {
    console.error('Backend executable not found:', exePath)
    return
  }

  backendPort = await findFreePort()

  const dataDir = path.join(app.getPath('userData'), 'backend-data')
  fs.mkdirSync(dataDir, { recursive: true })

  const logDir = path.join(app.getPath('userData'), 'logs')
  fs.mkdirSync(logDir, { recursive: true })
  const logFile = fs.openSync(path.join(logDir, 'backend.log'), 'w')

  backendProcess = spawn(exePath, [String(backendPort)], {
    env: { ...process.env, GENREGRID_DATA_DIR: dataDir, CORS_ORIGINS: '*' },
    stdio: ['ignore', logFile, logFile],
  })

  backendProcess.on('error', (err) => console.error('Backend error:', err))
  backendProcess.on('exit', (code) => console.log('Backend exited with code', code))

  await waitForBackend(backendPort, 120, 500)  // up to 60 s
}

// ── Window ───────────────────────────────────────────────────────────────────

async function createWindow(): Promise<void> {
  await startBackend()

  const win = new BrowserWindow({
    width: 1280,
    height: 900,
    minWidth: 900,
    minHeight: 600,
    backgroundColor: '#1a1a2e',
    title: 'GenreGrid',
    webPreferences: {
      preload: path.join(__dirname, 'preload.mjs'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  if (VITE_DEV_SERVER_URL) {
    win.loadURL(VITE_DEV_SERVER_URL)
  } else {
    win.loadURL('app://./index.html')
  }

}

app.whenReady().then(() => {
  // Serve bundled renderer files via app:// so absolute paths like /samples/... work
  protocol.handle('app', (request) => {
    const url = request.url.slice('app://./'.length) || 'index.html'
    const filePath = path.join(RENDERER_DIST, decodeURIComponent(url))
    return electronNet.fetch(`file://${filePath}`)
  })

  createWindow()
})

app.on('window-all-closed', () => {
  backendProcess?.kill()
  if (process.platform !== 'darwin') app.quit()
})

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow()
})

// ── IPC handlers ─────────────────────────────────────────────────────────────

// Synchronous — called from preload before the renderer loads
ipcMain.on('get-api-port', (event) => {
  event.returnValue = backendPort
})

// Write MIDI bytes to a temp file and return the path
ipcMain.handle('save-temp-file', async (_, { filename, data }: { filename: string; data: number[] }) => {
  const dir = path.join(app.getPath('temp'), 'genregrid')
  await fs.promises.mkdir(dir, { recursive: true })
  const filePath = path.join(dir, filename)
  await fs.promises.writeFile(filePath, Buffer.from(data))
  return filePath
})

// Build a 32×32 solid purple drag icon from raw RGBA pixels
function makeDragIcon(): ReturnType<typeof nativeImage.createFromBuffer> {
  const size = 32
  const buf = Buffer.alloc(size * size * 4)
  for (let i = 0; i < size * size; i++) {
    buf[i * 4 + 0] = 167  // R
    buf[i * 4 + 1] = 139  // G
    buf[i * 4 + 2] = 250  // B
    buf[i * 4 + 3] = 255  // A
  }
  return nativeImage.createFromBuffer(buf, { width: size, height: size })
}
const dragIcon = makeDragIcon()

// Initiate a native OS drag so DAWs receive a real file path.
// Called via sendSync so it stays in the same event frame as the dragstart gesture.
ipcMain.on('start-drag', (event, filePath: string) => {
  event.sender.startDrag({ file: filePath, icon: dragIcon })
  event.returnValue = null  // required to unblock sendSync in the renderer
})
