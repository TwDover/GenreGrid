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
import { ref } from 'vue'
import {
  buildManifest,
  type CustomInstrument,
  type InstrumentAssignments,
} from '../soundfonts/customInstruments'
import type { LayeredSamplerManifest } from '../soundfonts/layeredSampler'
import type { PlayerPart } from './useMidiPlayer'

// ── Custom-instrument library store ──────────────────────────────────────────
// Owns the user's uploaded instruments (persisted by the Electron main process
// under userData/instruments/) and the per-part assignments (persisted in
// localStorage). At play time `materialize()` reads an instrument's audio bytes over
// IPC and turns them into object URLs, so LayeredSampler loads them as blob: URLs —
// the same audio path the app already uses, which sidesteps the custom-scheme Web
// Audio silence bug seen on Linux Electron. See docs/custom-instruments-design.md.
// Storage is Electron-only for now; a plain browser build shows an empty library
// (OPFS support is a follow-up).

const ASSIGN_KEY = 'genregrid_instrument_assignments'

// Module-level singletons so every consumer shares one library + assignment map.
const instruments = ref<CustomInstrument[]>([])
const assignments = ref<InstrumentAssignments>(loadAssignments())
const panelOpen = ref(false)
let loadedOnce = false

function loadAssignments(): InstrumentAssignments {
  if (typeof localStorage === 'undefined') return { defaults: {} }
  try {
    const raw = localStorage.getItem(ASSIGN_KEY)
    if (raw) {
      const parsed = JSON.parse(raw) as InstrumentAssignments
      if (parsed && typeof parsed === 'object' && parsed.defaults) return parsed
    }
  } catch { /* corrupt/absent — start fresh */ }
  return { defaults: {} }
}

function persistAssignments() {
  if (typeof localStorage === 'undefined') return
  localStorage.setItem(ASSIGN_KEY, JSON.stringify(assignments.value))
}

function storageApi() {
  return typeof window !== 'undefined' ? window.electronAPI?.instruments : undefined
}

/** True when a persistent instrument store is available (the Electron shell). */
export function customInstrumentsSupported(): boolean {
  return !!storageApi()
}

// Cache of materialized instruments (object-URL manifests), keyed by id, so repeated
// plays don't re-read the bytes or leak new object URLs each time.
const materialized = new Map<string, LayeredSamplerManifest>()

/**
 * Read an instrument's audio over IPC and build a LayeredSampler manifest whose file
 * references are blob: object URLs. Cached per instrument. Returns null if the
 * instrument or the storage backend is unavailable. Use with LayeredSampler:
 *   new LayeredSampler({ baseUrl: '', manifest })
 */
async function materialize(id: string): Promise<LayeredSamplerManifest | null> {
  const cached = materialized.get(id)
  if (cached) return cached
  const inst = getInstrument(id)
  const api = storageApi()
  if (!inst || !api) return null

  const files = await api.read(id)
  const urlByName = new Map<string, string>()
  for (const f of files) {
    urlByName.set(f.name, URL.createObjectURL(new Blob([new Uint8Array(f.data)])))
  }
  const resolve = (v: string | string[]) =>
    Array.isArray(v) ? v.map(x => urlByName.get(x) ?? x) : (urlByName.get(v) ?? v)

  const manifest: LayeredSamplerManifest = {
    layers: inst.manifest.layers.map(l => ({
      maxVelocity: l.maxVelocity,
      urls: Object.fromEntries(Object.entries(l.urls).map(([note, v]) => [note, resolve(v)])),
    })),
  }
  materialized.set(id, manifest)
  return manifest
}

function uuid(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return `inst-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

/** Load the library index once (idempotent). Safe to call from any consumer. */
async function ensureLoaded(): Promise<void> {
  if (loadedOnce) return
  loadedOnce = true
  const api = storageApi()
  if (!api) return
  try {
    instruments.value = await api.list()
  } catch {
    instruments.value = []
  }
}

/**
 * Import dropped files as a new custom instrument. Folder structure is preserved in
 * each file's name (via webkitRelativePath) so velocity-layer subfolders map through
 * `buildManifest`. Returns the created instrument, or null if nothing usable was found
 * or storage is unavailable.
 */
async function importInstrument(
  name: string,
  kind: CustomInstrument['kind'],
  files: File[],
): Promise<CustomInstrument | null> {
  const api = storageApi()
  if (!api) throw new Error('Custom instruments need the desktop app.')

  const named = files.map(f => ({ file: f, path: relPath(f) }))
  const { manifest, mapped } = buildManifest(named.map(n => n.path))
  if (mapped === 0 || manifest.layers.length === 0) return null

  const id = uuid()
  const inst: CustomInstrument = { id, name: name.trim() || 'Untitled', kind, manifest, createdAt: Date.now() }

  const payload = await Promise.all(
    named
      .filter(n => /\.(mp3|wav|ogg|flac|m4a|aac)$/i.test(n.path))
      .map(async n => ({ name: n.path, data: [...new Uint8Array(await n.file.arrayBuffer())] })),
  )
  await api.save(inst, payload)
  instruments.value = [...instruments.value, inst]
  return inst
}

// The path used both for the manifest and for storage. Folder uploads carry a
// webkitRelativePath ("MyRhodes/hard/C4.mp3"); drop its redundant top segment so the
// stored/served path matches what buildManifest derived the layer folder from.
function relPath(f: File): string {
  const rel = (f as File & { webkitRelativePath?: string }).webkitRelativePath
  if (rel && rel.includes('/')) return rel.split('/').slice(1).join('/') || f.name
  return f.name
}

async function deleteInstrument(id: string): Promise<void> {
  const api = storageApi()
  if (api) await api.remove(id)
  instruments.value = instruments.value.filter(i => i.id !== id)
  materialized.delete(id)
  // Drop any assignments that referenced it.
  let changed = false
  for (const part of Object.keys(assignments.value.defaults) as PlayerPart[]) {
    if (assignments.value.defaults[part] === id) { delete assignments.value.defaults[part]; changed = true }
  }
  for (const style of Object.keys(assignments.value.perStyle ?? {})) {
    const m = assignments.value.perStyle![style]
    for (const part of Object.keys(m) as PlayerPart[]) {
      if (m[part] === id) { delete m[part]; changed = true }
    }
  }
  if (changed) persistAssignments()
}

/** Assign (or clear, with id=null) a custom instrument to a part — globally, or for a
 *  specific style when `styleId` is given. */
function assignPart(part: PlayerPart, id: string | null, styleId?: string): void {
  if (styleId) {
    assignments.value.perStyle ??= {}
    assignments.value.perStyle[styleId] ??= {}
    if (id) assignments.value.perStyle[styleId][part] = id
    else delete assignments.value.perStyle[styleId][part]
  } else {
    if (id) assignments.value.defaults[part] = id
    else delete assignments.value.defaults[part]
  }
  persistAssignments()
}

function getInstrument(id: string): CustomInstrument | undefined {
  return instruments.value.find(i => i.id === id)
}

export function useCustomInstruments() {
  return {
    instruments,
    assignments,
    panelOpen,
    ensureLoaded,
    importInstrument,
    deleteInstrument,
    assignPart,
    getInstrument,
    materialize,
    supported: customInstrumentsSupported,
  }
}
