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

  /** User custom-instrument storage (see docs/custom-instruments-design.md). Audio
   *  lives under userData/instruments/<id>/ and is served back over the gginstr://
   *  protocol; only the index (with manifests) round-trips through these calls. */
  instruments?: {
    /** Read the library index (instruments without their audio bytes). */
    list: () => Promise<import('./soundfonts/customInstruments').CustomInstrument[]>
    /** Persist one instrument + its audio files (name may include a sub-path). */
    save: (
      inst: import('./soundfonts/customInstruments').CustomInstrument,
      files: Array<{ name: string; data: number[] }>,
    ) => Promise<void>
    /** Delete an instrument and its audio. */
    remove: (id: string) => Promise<void>
    /** Read every audio file for an instrument (name may include a sub-path). */
    read: (id: string) => Promise<Array<{ name: string; data: number[] }>>
  }
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
