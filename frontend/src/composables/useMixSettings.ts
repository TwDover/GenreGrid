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
import type { MasterEqBands } from '../soundfonts/loader'
import { DEFAULT_PART_TONE, type PartTone } from '../soundfonts/partTone'
import type { PlayerPart } from './playerConstants'

// ── Mix settings store (roadmap 6.5) ─────────────────────────────────────────
// User-facing mix polish: a 3-band master EQ and a per-part tone preset. Global
// only (no per-style override, unlike InstrumentAssignments) — deliberately kept
// small per the roadmap's own risk note ("keep it to presets, not a console").
// Persists in localStorage like useSynthPatches.ts, so it works in the browser
// build too. Read directly as a module singleton by both playback paths
// (useMidiPlayer.ts for live, useOfflineRender.ts for export) — same pattern
// useSynthPatches/useCustomInstruments/useDrumKitPatches already use there.

const EQ_KEY = 'genregrid_master_eq'
const TONE_KEY = 'genregrid_part_tone'

export type PartToneAssignments = Partial<Record<PlayerPart, PartTone>>

const masterEQ = ref<MasterEqBands>(loadMasterEQ())
const partTone = ref<PartToneAssignments>(loadPartTone())

function loadMasterEQ(): MasterEqBands {
  if (typeof localStorage === 'undefined') return { low: 0, mid: 0, high: 0 }
  try {
    const raw = localStorage.getItem(EQ_KEY)
    const parsed = raw ? JSON.parse(raw) : null
    if (parsed && typeof parsed.low === 'number' && typeof parsed.mid === 'number' && typeof parsed.high === 'number') {
      return parsed
    }
  } catch { /* corrupt/absent — start flat */ }
  return { low: 0, mid: 0, high: 0 }
}

function loadPartTone(): PartToneAssignments {
  if (typeof localStorage === 'undefined') return {}
  try {
    const raw = localStorage.getItem(TONE_KEY)
    const parsed = raw ? JSON.parse(raw) : null
    if (parsed && typeof parsed === 'object') return parsed
  } catch { /* corrupt/absent — start empty */ }
  return {}
}

function persistMasterEQ() {
  if (typeof localStorage !== 'undefined') localStorage.setItem(EQ_KEY, JSON.stringify(masterEQ.value))
}
function persistPartTone() {
  if (typeof localStorage !== 'undefined') localStorage.setItem(TONE_KEY, JSON.stringify(partTone.value))
}

function setMasterEQBands(bands: MasterEqBands): void {
  masterEQ.value = bands
  persistMasterEQ()
}

function resetMasterEQ(): void {
  setMasterEQBands({ low: 0, mid: 0, high: 0 })
}

function setPartTone(part: PlayerPart, tone: PartTone): void {
  partTone.value = { ...partTone.value, [part]: tone }
  persistPartTone()
}

/** Resolve a part's tone setting, falling back to neutral/full amount if unset. */
function toneForPart(part: PlayerPart): PartTone {
  return partTone.value[part] ?? DEFAULT_PART_TONE
}

export function useMixSettings() {
  return { masterEQ, partTone, setMasterEQBands, resetMasterEQ, setPartTone, toneForPart }
}
