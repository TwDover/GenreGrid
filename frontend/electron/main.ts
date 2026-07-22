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
import http from 'http'
import path from 'path'
import fs from 'fs'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const RENDERER_DIST = path.join(__dirname, '../dist')
const VITE_DEV_SERVER_URL = process.env.VITE_DEV_SERVER_URL

// On Linux, Chromium's out-of-process (sandboxed) audio service stalls after the first
// buffer on some PipeWire/PulseAudio setups — the Web Audio graph keeps running (meters
// show signal, notes fire) but the hardware stream renders one blip then silence. Running
// the audio service in-process fixes it. Windows/macOS are unaffected, so limit to Linux.
if (process.platform === 'linux') {
  app.commandLine.appendSwitch('disable-features', 'AudioServiceOutOfProcess,AudioServiceSandbox')
}

// Register app:// as a privileged scheme so absolute paths (/samples/...) resolve correctly
// in the packaged app (file:// breaks absolute URL resolution)
protocol.registerSchemesAsPrivileged([
  { scheme: 'app', privileges: { secure: true, standard: true, supportFetchAPI: true } },
])

function getLogsDir(): string {
  const dir = path.join(app.getPath('userData'), 'logs')
  fs.mkdirSync(dir, { recursive: true })
  return dir
}

let backendProcess: ChildProcess | null = null
let backendPort = 8000  // default for dev (user runs backend manually)
// Set right before we deliberately end the backend (app quitting, update
// install) so its 'exit' handler can tell that apart from an actual crash.
let backendShutdownExpected = false

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

  const logDir = getLogsDir()
  const logFile = fs.openSync(path.join(logDir, 'backend.log'), 'w')

  backendProcess = spawn(exePath, [String(backendPort)], {
    env: { ...process.env, GENREGRID_DATA_DIR: dataDir, CORS_ORIGINS: '*' },
    stdio: ['ignore', logFile, logFile],
    // The backend is a console-subsystem exe (so devs can run it standalone
    // and see output); CREATE_NO_WINDOW keeps its blank console from popping
    // up behind the app on Windows. Output still lands in backend.log.
    windowsHide: true,
  })

  backendProcess.on('error', (err) => console.error('Backend error:', err))

  let backendReady = false
  backendProcess.on('exit', (code) => {
    console.log('Backend exited with code', code)
    // Only a crash while the app is still meant to be running is worth
    // interrupting the user for — closing the app (or restarting for an
    // update) also ends the backend, and that's expected, not an error.
    if (backendReady && !backendShutdownExpected) {
      dialog.showErrorBox(
        'Backend stopped',
        `The GenreGrid backend exited unexpectedly (code ${code}).\n\nGeneration will not work until you restart the app. Check logs at:\n${path.join(app.getPath('userData'), 'logs', 'backend.log')}`,
      )
    }
  })

  await waitForBackend(backendPort, 120, 500)  // up to 60 s
  backendReady = true
}

// ── Renderer static server ────────────────────────────────────────────────────
// The renderer is served over http://127.0.0.1:<port> rather than the app:// custom
// scheme. On Linux packaged Electron, the app:// origin breaks the Web Audio output path
// (the master DynamicsCompressor — and even a plain AudioContext destination — render
// digital silence to the speakers, while meters still show signal); an http origin plays
// correctly, exactly as it does in dev (Vite) and in a browser. Windows/macOS were fine
// with app://, but http works there too, so it's used on every platform for consistency.
const RENDERER_MIME: Record<string, string> = {
  '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript',
  '.css': 'text/css', '.json': 'application/json', '.wasm': 'application/wasm',
  '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif',
  '.svg': 'image/svg+xml', '.ico': 'image/x-icon', '.webp': 'image/webp',
  '.woff': 'font/woff', '.woff2': 'font/woff2', '.ttf': 'font/ttf',
  '.mp3': 'audio/mpeg', '.wav': 'audio/wav', '.ogg': 'audio/ogg', '.map': 'application/json',
}

function startRendererServer(): Promise<string> {
  return new Promise((resolve, reject) => {
    const server = http.createServer((req, res) => {
      try {
        const urlPath = decodeURIComponent((req.url || '/').split('?')[0])
        const rel = urlPath === '/' ? 'index.html' : urlPath.replace(/^\/+/, '')
        let filePath = path.join(RENDERER_DIST, rel)
        // Block path traversal, and fall back to index.html for unknown paths (SPA).
        if (!filePath.startsWith(RENDERER_DIST) || !fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
          filePath = path.join(RENDERER_DIST, 'index.html')
        }
        res.setHeader('Content-Type', RENDERER_MIME[path.extname(filePath).toLowerCase()] || 'application/octet-stream')
        fs.createReadStream(filePath).pipe(res)
      } catch {
        res.statusCode = 500
        res.end('Internal error')
      }
    })
    server.on('error', reject)
    server.listen(0, '127.0.0.1', () => {
      const port = (server.address() as nodeNet.AddressInfo).port
      resolve(`http://127.0.0.1:${port}/index.html`)
    })
  })
}

// ── Window ───────────────────────────────────────────────────────────────────

async function createWindow(): Promise<void> {
  console.log('[main] === GenreGrid starting ===')
  console.log('[main] isPackaged=', app.isPackaged, 'platform=', process.platform, 'resourcesPath=', process.resourcesPath)
  console.log('[main] RENDERER_DIST=', RENDERER_DIST, 'exists=', fs.existsSync(RENDERER_DIST))
  try {
    await startBackend()
    console.log('[main] backend ready on port', backendPort)
  } catch (e) {
    console.error('[main] backend start FAILED:', e)
  }

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
      // Never throttle the renderer when the window is unfocused/occluded — Electron's
      // default throttling suspends the audio render thread when the window loses focus
      // (e.g. clicking the terminal or DevTools), which stops playback after it starts.
      backgroundThrottling: false,
    },
  })

  // ── DEBUG: mirror the whole renderer console into the main-process stdout, so the full
  // renderer log (audio setup, errors, everything) shows in the terminal without DevTools.
  win.webContents.on('console-message', (_e, level, message) => {
    const tag = ['LOG', 'WARN', 'ERR', 'INFO'][level] ?? 'LOG'
    console.log(`[renderer:${tag}] ${message}`)
  })
  win.webContents.on('did-fail-load', (_e, code, desc, url) => {
    console.error(`[main] renderer FAILED to load: code=${code} "${desc}" url=${url}`)
  })
  win.webContents.on('did-finish-load', () => console.log('[main] renderer finished loading'))
  win.webContents.on('render-process-gone', (_e, d) => console.error('[main] render process gone:', d))

  // ── Developer keyboard shortcuts ────────────────────────────────────────────
  // Full list, documented so any dev knows what's available. Handled in the main
  // process (except the HUD toggle, which the renderer owns) so they work regardless
  // of focus. Ctrl also matches Cmd (meta) on macOS.
  const wc = win.webContents
  const SHORTCUTS: Array<[string, string]> = [
    ['Ctrl/Cmd + R', 'Reload the app'],
    ['Ctrl/Cmd + Shift + R', 'Hard reload (ignore cache)'],
    ['F12  /  Ctrl/Cmd + Shift + I', 'Toggle DevTools'],
    ['Ctrl/Cmd + Shift + D', 'Toggle the on-screen debug HUD (renderer)'],
    ['Ctrl/Cmd + =  /  + ', 'Zoom in'],
    ['Ctrl/Cmd + -', 'Zoom out'],
    ['Ctrl/Cmd + 0', 'Reset zoom'],
    ['F11', 'Toggle fullscreen'],
    ['Ctrl/Cmd + M', 'Minimize window'],
    ['Ctrl/Cmd + W  /  Ctrl/Cmd + Q', 'Quit the app'],
  ]
  console.log('[main] ── Keyboard shortcuts ──')
  for (const [combo, desc] of SHORTCUTS) console.log(`[main]   ${combo.padEnd(30)} ${desc}`)

  wc.on('before-input-event', (_e, input) => {
    if (input.type !== 'keyDown') return
    const k = input.key.toLowerCase()
    const mod = input.control || input.meta      // Ctrl on Win/Linux, Cmd on macOS
    if (k === 'f12' || (mod && input.shift && k === 'i')) wc.toggleDevTools()
    else if (mod && input.shift && k === 'r') wc.reloadIgnoringCache()
    else if (mod && k === 'r') wc.reload()
    // Ctrl+Shift+D (HUD) is intentionally NOT handled here — it falls through to the
    // renderer, which owns the HUD and toggles its own visibility.
    else if (mod && (k === '=' || k === '+')) wc.setZoomLevel(wc.getZoomLevel() + 0.5)
    else if (mod && k === '-') wc.setZoomLevel(wc.getZoomLevel() - 0.5)
    else if (mod && k === '0') wc.setZoomLevel(0)
    else if (k === 'f11') win.setFullScreen(!win.isFullScreen())
    else if (mod && k === 'm') win.minimize()
    else if (mod && (k === 'w' || k === 'q')) app.quit()
  })

  let rendererUrl: string
  if (VITE_DEV_SERVER_URL) {
    rendererUrl = VITE_DEV_SERVER_URL
  } else {
    rendererUrl = await startRendererServer()
    console.log('[main] renderer static server:', rendererUrl)
  }
  console.log('[main] loading renderer URL:', rendererUrl)
  win.loadURL(rendererUrl)
  // DevTools NOT auto-opened — a detached DevTools window steals focus and (with default
  // throttling) can suspend the audio window. Open it yourself with F12 if needed.
}

// ── Auto-update ──────────────────────────────────────────────────────────────
// Checks GitHub Releases (electron-builder publish config) for a newer version,
// downloads it in the background, and offers a restart. Skipped on macOS: the
// builds are unsigned and Squirrel.Mac refuses unsigned updates — Mac users
// update via the Releases page. Failures are logged, never surfaced as errors.
async function setupAutoUpdate(): Promise<void> {
  if (!app.isPackaged || process.platform === 'darwin') return
  try {
    const { autoUpdater } = await import('electron-updater')
    autoUpdater.autoDownload = true
    autoUpdater.on('update-downloaded', (info) => {
      const choice = dialog.showMessageBoxSync({
        type: 'info',
        buttons: ['Restart now', 'Later'],
        defaultId: 0,
        cancelId: 1,
        message: `GenreGrid ${info.version} is ready`,
        detail: 'The update has been downloaded. Restart to apply it — or keep working and it installs on next launch.',
      })
      if (choice === 0) {
        backendShutdownExpected = true
        autoUpdater.quitAndInstall()
      }
    })
    await autoUpdater.checkForUpdates()
  } catch (err) {
    console.error('Auto-update check failed (non-fatal):', err)
  }
}

// Manual "Check for updates" from the renderer. Returns a status the UI can
// show inline; when an update exists, the download starts and the existing
// update-downloaded dialog (registered in setupAutoUpdate) offers the restart.
ipcMain.handle('check-for-updates', async () => {
  const version = app.getVersion()
  if (!app.isPackaged) return { status: 'dev', version }
  if (process.platform === 'darwin') return { status: 'unsupported', version }
  try {
    const { autoUpdater } = await import('electron-updater')
    const result = await autoUpdater.checkForUpdates()
    const latest = result?.updateInfo?.version
    if (latest && latest !== version) return { status: 'downloading', version, latest }
    return { status: 'uptodate', version }
  } catch (err: any) {
    console.error('Manual update check failed:', err)
    return { status: 'error', version, message: String(err?.message ?? err) }
  }
})

app.whenReady().then(() => {
  // Serve bundled renderer files via app:// so absolute paths like /samples/... work
  protocol.handle('app', (request) => {
    const url = request.url.slice('app://./'.length) || 'index.html'
    const filePath = path.join(RENDERER_DIST, decodeURIComponent(url))
    return electronNet.fetch(`file://${filePath}`)
  })

  createWindow()
  setupAutoUpdate()
})

app.on('window-all-closed', () => {
  backendShutdownExpected = true
  backendProcess?.kill()
  if (process.platform !== 'darwin') app.quit()
})

// Safety net for quit paths that don't go through window-all-closed first
// (macOS Cmd+Q fires this before the window closes, OS session end, etc.) —
// idempotent, so setting it here too is harmless if window-all-closed already did.
app.on('before-quit', () => {
  backendShutdownExpected = true
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

// Append one renderer-side error to logs/renderer-errors.log, next to
// backend.log — a durable record even if the app closes before anyone opens
// the in-app error log panel. Appended (not truncated) across the whole
// session, capped so a runaway error loop can't grow it unbounded.
const RENDERER_LOG_MAX_BYTES = 2 * 1024 * 1024   // 2 MB
ipcMain.handle('log-renderer-error', async (_, entry: { timestamp: string; context: string; message: string; stack?: string }) => {
  try {
    const logPath = path.join(getLogsDir(), 'renderer-errors.log')
    try {
      const { size } = await fs.promises.stat(logPath)
      if (size > RENDERER_LOG_MAX_BYTES) await fs.promises.unlink(logPath)
    } catch { /* file doesn't exist yet — fine */ }
    const line = `[${entry.timestamp}] ${entry.context}: ${entry.message}${entry.stack ? `\n${entry.stack}` : ''}\n\n`
    await fs.promises.appendFile(logPath, line, 'utf-8')
  } catch (err) {
    console.error('Failed to write renderer error log:', err)
  }
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
