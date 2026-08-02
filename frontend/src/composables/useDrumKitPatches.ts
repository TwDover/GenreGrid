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
import { BUILTIN_KITS, builtinKitPatch, type DrumCharacter, type DrumKitPatch } from '../soundfonts/synthDrums'
import { drumCharacterForStyle } from '../soundfonts/drums'
import { resolvePartInstrument, type InstrumentAssignments } from '../soundfonts/customInstruments'

// ── Saved-drum-kit-patch store (drum voice designer) ─────────────────────────
// The drum-side analog of useSynthPatches.ts: owns the user's designed
// DrumKitPatches and their style assignment. This is a NEW, independent
// assignment axis from useCustomInstruments' 'drums' assignment — that one
// layers real sample files over the synth kit (makeHybridKit); this one picks
// which SYNTH patch underlies the kit in the first place. Both apply together.
//
// There's only ever one drum kit per style (unlike melodic parts), so — unlike
// useSynthPatches — there's no per-part dimension here. `resolvePartInstrument`
// is still reused as-is (with the fixed part 'drums') for its default/per-style
// precedence rules and because it's already unit-tested.

export interface SavedKit {
  id: string
  name: string
  patch: DrumKitPatch
  createdAt: number
}

const LIB_KEY = 'genregrid_drum_kits'
const ASSIGN_KEY = 'genregrid_drum_kit_assignments'
const PART = 'drums'

const kits = ref<SavedKit[]>(loadKits())
const assignments = ref<InstrumentAssignments>(loadAssignments())

function loadKits(): SavedKit[] {
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

function persistKits() {
  if (typeof localStorage !== 'undefined') localStorage.setItem(LIB_KEY, JSON.stringify(kits.value))
}
function persistAssignments() {
  if (typeof localStorage !== 'undefined') localStorage.setItem(ASSIGN_KEY, JSON.stringify(assignments.value))
}

function uuid(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return `kit-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

const clone = (p: DrumKitPatch): DrumKitPatch => JSON.parse(JSON.stringify(p))

/** Save `patch` under `name`. Overwrites the existing kit of the same (trimmed)
 *  name so re-saving a tweaked kit updates it in place rather than piling up
 *  duplicates. */
function saveKit(name: string, patch: DrumKitPatch): SavedKit {
  const trimmed = name.trim() || 'Untitled'
  const existing = kits.value.find(k => k.name === trimmed)
  if (existing) {
    const updated: SavedKit = { ...existing, patch: clone(patch) }
    kits.value = kits.value.map(k => (k.id === existing.id ? updated : k))
    persistKits()
    return updated
  }
  const saved: SavedKit = { id: uuid(), name: trimmed, patch: clone(patch), createdAt: Date.now() }
  kits.value = [...kits.value, saved]
  persistKits()
  return saved
}

function deleteKit(id: string): void {
  kits.value = kits.value.filter(k => k.id !== id)
  persistKits()
  // Drop any assignment that referenced it, so a style doesn't point at a ghost.
  let changed = false
  if (assignments.value.defaults[PART] === id) { delete assignments.value.defaults[PART]; changed = true }
  for (const style of Object.keys(assignments.value.perStyle ?? {})) {
    const m = assignments.value.perStyle![style]
    if (m[PART] === id) { delete m[PART]; changed = true }
  }
  if (changed) persistAssignments()
}

/** Assign (or clear, with id=null) a kit to play — globally, or for one style when
 *  `styleId` is given. Mirrors useSynthPatches.assignPatch: a per-style clear
 *  records '' ("style default here") so it beats the all-styles default. `id` is
 *  either a saved-kit id or a built-in character slug. */
function assignKit(id: string | null, styleId?: string): void {
  if (styleId) {
    assignments.value.perStyle ??= {}
    assignments.value.perStyle[styleId] ??= {}
    assignments.value.perStyle[styleId][PART] = id ?? ''
  } else if (id) {
    assignments.value.defaults[PART] = id
  } else {
    delete assignments.value.defaults[PART]
  }
  persistAssignments()
}

function getKit(id: string): SavedKit | undefined {
  return kits.value.find(k => k.id === id)
}

/** The drum-kit patch to play under `styleId`: a per-style/default assignment
 *  (saved kit or built-in character) wins, else the style's usual character. */
function resolveKitForStyle(styleId: string | undefined): DrumKitPatch {
  const r = resolvePartInstrument(assignments.value, styleId, PART, null)
  if (r.source === 'custom') {
    const saved = getKit(r.id)
    if (saved) return saved.patch
    if (r.id in BUILTIN_KITS) return builtinKitPatch(r.id as DrumCharacter)
  }
  return builtinKitPatch(drumCharacterForStyle(styleId))
}

/** Built-in kit characters offered in the assignment dropdown (id = slug). */
export function builtinKitOptions(): { id: string; label: string }[] {
  return Object.entries(BUILTIN_KITS).map(([id, e]) => ({ id, label: e.label }))
}

/** The saved-kit or built-in id currently assigned (for the assignment UI's select).
 *  Returns undefined when nothing is assigned, '' for an explicit per-style "default". */
function assignedId(styleId: string | undefined, scope: 'all' | 'style'): string | undefined {
  if (scope !== 'style') return assignments.value.defaults[PART]
  const perStyle = styleId ? assignments.value.perStyle?.[styleId]?.[PART] : undefined
  return perStyle !== undefined ? perStyle : assignments.value.defaults[PART]
}

export function useDrumKitPatches() {
  return {
    kits,
    assignments,
    saveKit,
    deleteKit,
    assignKit,
    getKit,
    resolveKitForStyle,
    assignedId,
  }
}
