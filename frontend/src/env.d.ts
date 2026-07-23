/// <reference types="vite/client" />

// Ambient (global) type declarations that let the renderer reach the Electron
// preload bridge and custom Vite env vars without `as any` casts. This file is
// intentionally a script, not a module (no import/export at top level), so the
// interfaces below merge into the global scope and augment lib/vite typings.
// The bridge is exposed by electron/preload.ts via
// contextBridge.exposeInMainWorld('electronAPI', …); keep ElectronAPI in sync.

/** Shape of the object exposed on `window.electronAPI` by electron/preload.ts. */
interface ElectronAPI {
  isElectron: true
  apiPort: number
  saveTempFile: (filename: string, data: number[]) => Promise<string>
  startDrag: (filePath: string) => void
  checkForUpdates: () => Promise<{ status: string; version: string; latest?: string; message?: string }>
  logRendererError: (entry: { timestamp: string; context: string; message: string; stack?: string }) => Promise<void>
}

/** Custom Vite env vars (merges with vite/client's ImportMetaEnv). */
interface ImportMetaEnv {
  readonly VITE_API_URL?: string
}

interface Window {
  /** Present only when running inside the Electron shell; undefined in a browser. */
  electronAPI?: ElectronAPI
  /** File System Access API — not in every TS lib target; used by PartCard's save flow. */
  showSaveFilePicker?: (options?: {
    suggestedName?: string
    types?: Array<{ description?: string; accept: Record<string, string[]> }>
  }) => Promise<FileSystemFileHandle>
}
