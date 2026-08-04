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
// Browser-build storage backend for custom instruments (roadmap 6.3) — mirrors
// the Electron IPC surface (electron/main.ts's instruments-* handlers) exactly:
// the same four methods, the same on-disk-shaped layout (an index.json of
// metadata-only CustomInstrument entries, one subdirectory per instrument
// holding its raw audio files). useCustomInstruments.ts's storageApi() picks
// whichever backend is available; the rest of the store needs no changes.
//
// Uses the Origin Private File System (OPFS) — a sandboxed, origin-scoped
// filesystem no other site/tab can read, reached via
// navigator.storage.getDirectory(). Unlike a FileSystemSyncAccessHandle (worker-
// only), createWritable() works from the main thread, so this needs no worker.
import type { CustomInstrument } from './customInstruments'

export interface StoredInstrumentFile { name: string; data: number[] }

export interface InstrumentStorageApi {
  list(): Promise<CustomInstrument[]>
  save(inst: CustomInstrument, files: StoredInstrumentFile[]): Promise<void>
  remove(id: string): Promise<void>
  read(id: string): Promise<StoredInstrumentFile[]>
}

const ROOT_DIR = 'instruments'
const INDEX_FILE = 'index.json'

function opfsSupported(): boolean {
  return typeof navigator !== 'undefined' && !!navigator.storage &&
    typeof navigator.storage.getDirectory === 'function'
}

// Cached so repeated calls in one session don't re-resolve the root handle;
// resettable for test isolation (each test gets its own mock filesystem).
let rootDirPromise: Promise<FileSystemDirectoryHandle> | null = null

function instrumentsDir(): Promise<FileSystemDirectoryHandle> {
  rootDirPromise ??= (async () => {
    const root = await navigator.storage.getDirectory()
    return root.getDirectoryHandle(ROOT_DIR, { create: true })
  })()
  return rootDirPromise
}

/** Test-only: forget the cached root handle so the next call re-resolves it
 *  (each test installs its own mock `navigator.storage`). */
export function __resetOpfsInstrumentStorageForTests(): void {
  rootDirPromise = null
}

async function readIndex(dir: FileSystemDirectoryHandle): Promise<CustomInstrument[]> {
  try {
    const handle = await dir.getFileHandle(INDEX_FILE)
    const text = await (await handle.getFile()).text()
    const parsed = JSON.parse(text)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []   // no index yet, or corrupt — start fresh (mirrors main.ts's try/catch)
  }
}

async function writeIndex(dir: FileSystemDirectoryHandle, list: CustomInstrument[]): Promise<void> {
  const handle = await dir.getFileHandle(INDEX_FILE, { create: true })
  const writable = await handle.createWritable()
  await writable.write(JSON.stringify(list))
  await writable.close()
}

/** Walk `path` ("hard/C4.mp3") from `dir`, creating intermediate directories
 *  when `create` is true, and return the final file handle — the same
 *  sub-path support `save-temp-file`'s Electron counterpart gives folder
 *  uploads (velocity-layer subfolders). */
export async function fileHandleForPath(
  dir: FileSystemDirectoryHandle, path: string, create: boolean,
): Promise<FileSystemFileHandle> {
  const parts = path.split('/').filter(Boolean)
  let cur = dir
  for (let i = 0; i < parts.length - 1; i++) {
    cur = await cur.getDirectoryHandle(parts[i], { create })
  }
  return cur.getFileHandle(parts[parts.length - 1], { create })
}

/** Recursively collect every file under `dir` as {name: relative path, data:
 *  bytes} — the OPFS equivalent of main.ts's recursive instrument-folder read. */
export async function readAllFiles(dir: FileSystemDirectoryHandle, prefix = ''): Promise<StoredInstrumentFile[]> {
  const out: StoredInstrumentFile[] = []
  for await (const [name, handle] of dir.entries()) {
    const relPath = prefix ? `${prefix}/${name}` : name
    if (handle.kind === 'directory') {
      out.push(...await readAllFiles(handle as FileSystemDirectoryHandle, relPath))
    } else {
      const file = await (handle as FileSystemFileHandle).getFile()
      out.push({ name: relPath, data: [...new Uint8Array(await file.arrayBuffer())] })
    }
  }
  return out
}

async function list(): Promise<CustomInstrument[]> {
  return readIndex(await instrumentsDir())
}

async function save(inst: CustomInstrument, files: StoredInstrumentFile[]): Promise<void> {
  const root = await instrumentsDir()
  const instDir = await root.getDirectoryHandle(inst.id, { create: true })
  for (const f of files) {
    const fileHandle = await fileHandleForPath(instDir, f.name, true)
    const writable = await fileHandle.createWritable()
    await writable.write(new Uint8Array(f.data))
    await writable.close()
  }
  const index = await readIndex(root)
  await writeIndex(root, [...index.filter(i => i.id !== inst.id), inst])
}

async function remove(id: string): Promise<void> {
  const root = await instrumentsDir()
  try {
    await root.removeEntry(id, { recursive: true })
  } catch { /* already gone */ }
  const index = await readIndex(root)
  await writeIndex(root, index.filter(i => i.id !== id))
}

async function read(id: string): Promise<StoredInstrumentFile[]> {
  const root = await instrumentsDir()
  try {
    const instDir = await root.getDirectoryHandle(id)
    return await readAllFiles(instDir)
  } catch {
    return []
  }
}

/** The OPFS-backed instrument storage API, or undefined if OPFS isn't
 *  available in this browser (older Safari/Firefox, or a non-secure context) —
 *  the same graceful-degradation shape as the Electron backend being absent. */
export function opfsInstrumentStorage(): InstrumentStorageApi | undefined {
  return opfsSupported() ? { list, save, remove, read } : undefined
}
