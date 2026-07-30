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
import { builtinPatch, BUILTIN_PATCHES, type SynthPatch } from '../soundfonts/synthPatch'
import { resolvePartInstrument, type InstrumentAssignments } from '../soundfonts/customInstruments'
import type { PlayerPart } from './useMidiPlayer'

// ── Saved-synth-patch store (roadmap 6.6) ────────────────────────────────────
// Owns the user's designed patches and their per-part assignments. Unlike custom
// instruments (audio bytes over Electron IPC), a patch is pure JSON, so BOTH the
// library and the assignments persist in localStorage — which means patches work in
// the browser build too, not only the desktop shell.
//
// Assignments reuse the custom-instrument shape + resolver (defaults + per-style
// overrides, '' = "built-in for this style"), so the precedence rules are identical
// and already unit-tested. A resolved id maps to a patch in the library; the live
// player builds it with buildSynthFromPatch. Assigned patches DON'T render in offline
// export yet — the same gap custom instruments have (useOfflineRender is a separate,
// style-only path); unifying export is its own effort.

export interface SavedPatch {
  id: string
  name: string
  patch: SynthPatch
  createdAt: number
}

const LIB_KEY = 'genregrid_synth_patches'
const ASSIGN_KEY = 'genregrid_synth_patch_assignments'

// The parts a patch can drive — every melodic part (drums are a synth kit, not a voice).
export const PATCHABLE_PARTS: readonly PlayerPart[] = ['chords', 'bass', 'melody', 'arpeggio', 'pads', 'counter_melody']

// Module-level singletons so the designer, the transport, and the player share state.
const patches = ref<SavedPatch[]>(loadPatches())
const assignments = ref<InstrumentAssignments>(loadAssignments())

function loadPatches(): SavedPatch[] {
  if (typeof localStorage === 'undefined') return []
  try {
    const raw = localStorage.getItem(LIB_KEY)
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function loadAssignments(): InstrumentAssignments {
  if (typeof localStorage === 'undefined') return { defaults: {} }
  try {
    const raw = localStorage.getItem(ASSIGN_KEY)
    const parsed = raw ? (JSON.parse(raw) as InstrumentAssignments) : null
    if (parsed && typeof parsed === 'object' && parsed.defaults) return parsed
  } catch { /* corrupt/absent — start fresh */ }
  return { defaults: {} }
}

function persistPatches() {
  if (typeof localStorage !== 'undefined') localStorage.setItem(LIB_KEY, JSON.stringify(patches.value))
}
function persistAssignments() {
  if (typeof localStorage !== 'undefined') localStorage.setItem(ASSIGN_KEY, JSON.stringify(assignments.value))
}

function uuid(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return `patch-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

const clone = (p: SynthPatch): SynthPatch => JSON.parse(JSON.stringify(p))

/** Save `patch` under `name`. Overwrites the existing patch of the same (trimmed) name
 *  so re-saving a tweaked patch updates it in place rather than piling up duplicates. */
function savePatch(name: string, patch: SynthPatch): SavedPatch {
  const trimmed = name.trim() || 'Untitled'
  const existing = patches.value.find(p => p.name === trimmed)
  if (existing) {
    const updated: SavedPatch = { ...existing, patch: clone(patch) }
    patches.value = patches.value.map(p => (p.id === existing.id ? updated : p))
    persistPatches()
    return updated
  }
  const saved: SavedPatch = { id: uuid(), name: trimmed, patch: clone(patch), createdAt: Date.now() }
  patches.value = [...patches.value, saved]
  persistPatches()
  return saved
}

function deletePatch(id: string): void {
  patches.value = patches.value.filter(p => p.id !== id)
  persistPatches()
  // Drop any assignment that referenced it, so a part doesn't point at a ghost.
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

/** Assign (or clear, with id=null) a saved patch to a part — globally, or for one style
 *  when `styleId` is given. Mirrors useCustomInstruments.assignPart: a per-style clear
 *  records '' ("built-in here") so it beats the all-styles default. */
function assignPatch(part: PlayerPart, id: string | null, styleId?: string): void {
  if (styleId) {
    assignments.value.perStyle ??= {}
    assignments.value.perStyle[styleId] ??= {}
    assignments.value.perStyle[styleId][part] = id ?? ''
  } else if (id) {
    assignments.value.defaults[part] = id
  } else {
    delete assignments.value.defaults[part]
  }
  persistAssignments()
}

function getPatch(id: string): SavedPatch | undefined {
  return patches.value.find(p => p.id === id)
}

/** The patch a part should play under `styleId`, or null for the built-in voice.
 *  Reuses the custom-instrument resolver for identical per-style/default precedence.
 *  An assignment id is either a saved-library id or a built-in patch slug. */
function resolvePatchForPart(styleId: string | undefined, part: PlayerPart): SynthPatch | null {
  const r = resolvePartInstrument(assignments.value, styleId, part, null)
  if (r.source !== 'custom') return null
  return getPatch(r.id)?.patch ?? builtinPatch(r.id) ?? null
}

// ── Assignable options + style kits ───────────────────────────────────────────

/** Built-in patches offered in the assignment dropdown (id = slug). */
export function builtinPatchOptions(): { id: string; label: string }[] {
  return Object.entries(BUILTIN_PATCHES).map(([id, e]) => ({ id, label: e.label }))
}

// A style's suggested patches per part (built-in slugs). Applying a kit assigns these
// as per-style overrides, so it only affects the current style and is fully reversible
// (set a part back to Built-in). Opt-in, so nothing changes until the user applies it.
const STYLE_KITS: Record<string, Partial<Record<PlayerPart, string>>> = {
  dark_trap: { bass: '808_trap' },
  drill: { bass: '808_trap' },
  grime: { bass: '808_trap' },
  jersey_club: { bass: '808_trap' },
  trap_soul: { bass: '808_sub' },
  cloud_rap: { bass: '808_sub' },
  hip_hop: { bass: '808_sub' },
  boom_bap: { bass: '808_sub' },
  reggaeton: { bass: '808_sub' },
  dancehall: { bass: '808_sub' },
  drum_and_bass: { bass: 'reese_bass' },
  house: { bass: 'acid_bass' },
  techno: { bass: 'acid_bass' },
  synthwave: { bass: 'synth_bass', pads: 'warm_pad', melody: 'supersaw_lead' },
  future_bass: { pads: 'warm_pad', melody: 'supersaw_lead' },
  hyperpop: { melody: 'supersaw_lead' },
  ambient: { pads: 'warm_pad' },
  dark_ambient: { pads: 'warm_pad' },
  cinematic: { pads: 'warm_pad' },
}

/** The suggested kit for a style as [part, patch label] rows, or [] if none. */
export function styleKitFor(styleId: string | undefined): { part: PlayerPart; label: string }[] {
  const kit = styleId ? STYLE_KITS[styleId] : undefined
  if (!kit) return []
  return (Object.keys(kit) as PlayerPart[]).map(part => ({ part, label: BUILTIN_PATCHES[kit[part]!]?.label ?? kit[part]! }))
}

/** Assign a style's suggested kit as per-style overrides. Returns the parts assigned. */
function applyStyleKit(styleId: string): PlayerPart[] {
  const kit = STYLE_KITS[styleId]
  if (!kit) return []
  const parts = Object.keys(kit) as PlayerPart[]
  for (const part of parts) assignPatch(part, kit[part]!, styleId)
  return parts
}

/** The saved-patch id currently assigned to a part (for the assignment UI's dropdowns).
 *  Returns undefined when nothing is assigned, '' for an explicit per-style "built-in". */
function assignedId(styleId: string | undefined, part: PlayerPart, scope: 'all' | 'style'): string | undefined {
  if (scope !== 'style') return assignments.value.defaults[part]
  const perStyle = styleId ? assignments.value.perStyle?.[styleId]?.[part] : undefined
  return perStyle !== undefined ? perStyle : assignments.value.defaults[part]
}

export function useSynthPatches() {
  return {
    patches,
    assignments,
    savePatch,
    deletePatch,
    assignPatch,
    getPatch,
    resolvePatchForPart,
    assignedId,
    applyStyleKit,
  }
}
