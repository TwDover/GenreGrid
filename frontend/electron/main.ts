/*
 * GenreGrid — a style-based MIDI generator.
 * Copyright (C) 2026 Tw Dover
 *
 * This program is free software: you can redistribute it and/or modify it under
 * the terms of the GNU General Public License as published by the Free Software
 * Foundation, either version 3 of the License, or (at your option) any later
 * version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
 * <https://www.gnu.org/licenses/> for details.
 */
import { app, BrowserWindow, dialog, ipcMain, nativeImage, protocol, net as electronNet } from 'electron'
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

// Wait until the backend HTTP API is responding (not just TCP-open)
function waitForBackend(port: number, retries = 120, delayMs = 500): Promise<void> {
  return new Promise((resolve, reject) => {
    const attempt = (n: number) => {
      electronNet.fetch(`http://127.0.0.1:${port}/health`)
        .then(r => { if (r.ok) resolve(); else throw new Error(`HTTP ${r.status}`) })
        .catch(() => {
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
    dialog.showErrorBox(
      'Backend not found',
      `Could not find the backend executable at:\n${exePath}\n\nThe app will open but generation will not work. Please reinstall GenreGrid.`,
    )
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

  let backendReady = false
  backendProcess.on('exit', (code) => {
    console.log('Backend exited with code', code)
    if (backendReady) {
      dialog.showErrorBox(
        'Backend stopped',
        `The GenreGrid backend exited unexpectedly (code ${code}).\n\nGeneration will not work until you restart the app. Check logs at:\n${path.join(app.getPath('userData'), 'logs', 'backend.log')}`,
      )
    }
  })

  await waitForBackend(backendPort, 120, 500)  // up to 60 s
  backendReady = true
}

// ── Window ───────────────────────────────────────────────────────────────────

async function createWindow(): Promise<void> {
  await startBackend()

  const win = new BrowserWindow({
    width: 1280,
    height: 900,
    minWidth: 900,
    minHeight: 600,
    backgroundColor: '#000000',
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
    buf[i * 4 + 0] = 0    // R
    buf[i * 4 + 1] = 200  // G
    buf[i * 4 + 2] = 255  // B
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
