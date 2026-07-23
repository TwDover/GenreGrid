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
import type { LayeredSamplerManifest, VelocityLayer } from './layeredSampler'
import type { PlayerPart } from '../composables/useMidiPlayer'

// ── User-uploaded custom instruments: pure core ──────────────────────────────
// Turns a bag of user-dropped audio files into a LayeredSampler manifest, and
// resolves which instrument (built-in registry voice or a user instrument) plays a
// part. No audio, no storage, no framework here — just the mapping rules, so they
// can be unit-tested without an AudioContext or Electron. See
// docs/custom-instruments-design.md.

/** A user instrument as stored in the library index (audio bytes live separately,
 *  addressed by the manifest's file names relative to the instrument's base URL). */
export interface CustomInstrument {
  id: string
  name: string
  kind: 'melodic' | 'bass' | 'drums'
  manifest: LayeredSamplerManifest
  createdAt: number
}

/** Per-part instrument assignments: a global default map plus optional per-style
 *  overrides. Values are custom-instrument ids. */
export interface InstrumentAssignments {
  defaults: Partial<Record<PlayerPart, string>>
  perStyle?: Record<string, Partial<Record<PlayerPart, string>>>
}

const AUDIO_EXT = /\.(mp3|wav|ogg|flac|m4a|aac)$/i
export function isAudioFile(name: string): boolean {
  return AUDIO_EXT.test(name)
}

/** Parsed pieces of a sample filename: the pitch, an optional velocity-layer hint,
 *  and an optional round-robin index. Any of them may be absent. */
export interface ParsedSampleName {
  note: string | null       // normalised, e.g. "C4", "A#3"
  layer: string | null      // velocity-layer hint from a folder or _vN / soft|hard token
  rr: number | null         // round-robin index (1-based) from _rrN
}

// A note token: letter A–G, optional accidental (# / s = sharp, b = flat), octave
// (0–8, optionally negative), not glued to more letters/digits on the note side.
const NOTE_RE = /(?:^|[^A-Za-z0-9])([A-Ga-g])(#|s|b)?(-?[0-8])(?![0-9A-Za-z])/g

/** Extract note / velocity-layer / round-robin from a file path. `path` may include a
 *  folder (e.g. "hard/C4.mp3"); the folder is used as a velocity-layer hint. */
export function parseSampleName(path: string): ParsedSampleName {
  const parts = path.split('/')
  const base = parts[parts.length - 1].replace(AUDIO_EXT, '')
  const folder = parts.length > 1 ? parts[parts.length - 2].toLowerCase() : ''

  // Note: take the LAST note-like token so a prefix like "Piano" or "Bass" can't win.
  let note: string | null = null
  for (const m of base.matchAll(NOTE_RE)) {
    const acc = m[2] === 's' ? '#' : (m[2] ?? '')
    note = `${m[1].toUpperCase()}${acc}${m[3]}`
  }

  const rrMatch = base.match(/[._-]rr(\d+)/i)
  const rr = rrMatch ? parseInt(rrMatch[1], 10) : null

  // Layer hint: an explicit velocity token in the name, else the containing folder
  // if it looks like a dynamics label (soft/hard/mf/…), else a _vN group.
  const DYN = /(soft|hard|quiet|loud|pp|mp|mf|ff|p|f|v\d+)/i
  const nameDyn = base.match(/[._-](soft|hard|quiet|loud|pp|mp|mf|ff|v\d+)\b/i)
  let layer: string | null = nameDyn ? nameDyn[1].toLowerCase() : null
  if (!layer && folder && DYN.test(folder)) layer = folder

  return { note, layer, rr }
}

// Order velocity-layer hints from softest to loudest so we can assign ascending
// velocity ceilings. Unknown labels sort after known ones, stably.
const DYN_ORDER = ['pp', 'p', 'soft', 'quiet', 'mp', 'v1', 'mf', 'v2', 'v3', 'v4', 'f', 'loud', 'hard', 'ff']
function dynRank(label: string): number {
  const i = DYN_ORDER.indexOf(label.toLowerCase())
  return i === -1 ? DYN_ORDER.length : i
}

export interface BuildManifestResult {
  manifest: LayeredSamplerManifest
  mapped: number       // files placed into the manifest
  skipped: string[]    // non-audio / unusable paths
}

/**
 * Build a LayeredSampler manifest from user-dropped files.
 *
 * - **T1 (one shot):** a single file with no parseable note → mapped to C4 and
 *   pitch-shifted across the keyboard.
 * - **T2 (note-named):** files named by note → one zone per note.
 * - **T3 (velocity/round-robin):** files grouped by a velocity hint (folder or _vN /
 *   soft|hard) become velocity layers; `_rrN` become round-robins within a note+layer.
 *
 * Returns the manifest plus counts. `defaultRoot` is where an un-pitched one-shot lands.
 */
export function buildManifest(paths: string[], defaultRoot = 'C4'): BuildManifestResult {
  const audio = paths.filter(isAudioFile)
  const skipped = paths.filter(p => !isAudioFile(p))

  if (audio.length === 0) {
    return { manifest: { layers: [] }, mapped: 0, skipped }
  }

  const parsed = audio.map(p => ({ path: p, ...parseSampleName(p) }))
  const anyNote = parsed.some(p => p.note)

  // One-shot: a lone file (or files with no notes at all) → single zone at the root.
  if (!anyNote) {
    const layer: VelocityLayer = {
      maxVelocity: 1,
      urls: { [defaultRoot]: audio.length === 1 ? audio[0] : audio },
    }
    return { manifest: { layers: [layer] }, mapped: audio.length, skipped }
  }

  // Group by velocity-layer hint (a single group when none are labelled).
  const byLayer = new Map<string, typeof parsed>()
  for (const p of parsed) {
    const key = p.layer ?? ''
    if (!byLayer.has(key)) byLayer.set(key, [])
    byLayer.get(key)!.push(p)
  }

  const layerKeys = [...byLayer.keys()].sort((a, b) => dynRank(a) - dynRank(b))
  const layers: VelocityLayer[] = layerKeys.map((key, idx) => {
    // Ascending, evenly-spaced ceilings; the top layer always reaches 1.
    const maxVelocity = idx === layerKeys.length - 1 ? 1 : (idx + 1) / layerKeys.length
    const urls: Record<string, string | string[]> = {}
    for (const p of byLayer.get(key)!) {
      const note = p.note ?? defaultRoot
      const existing = urls[note]
      if (existing === undefined) urls[note] = p.path
      else if (Array.isArray(existing)) existing.push(p.path)   // more round-robins
      else urls[note] = [existing, p.path]
    }
    // Sort round-robin arrays by their rr index so cycling is deterministic.
    for (const note of Object.keys(urls)) {
      const v = urls[note]
      if (Array.isArray(v)) {
        v.sort((a, b) => (parseSampleName(a).rr ?? 0) - (parseSampleName(b).rr ?? 0))
      }
    }
    return { maxVelocity, urls }
  })

  return { manifest: { layers }, mapped: audio.length, skipped }
}

/**
 * Resolve which instrument plays a part: a user assignment wins over the registry
 * voice. Returns either a custom-instrument id (with `source: 'custom'`) or the
 * built-in registry voice (`source: 'builtin'`, possibly null → synth). Resolution
 * order: per-style override → global default → registry voice.
 */
export function resolvePartInstrument(
  assignments: InstrumentAssignments | null,
  styleId: string | undefined,
  part: PlayerPart,
  registryVoice: string | null,
): { source: 'custom'; id: string } | { source: 'builtin'; voice: string | null } {
  if (assignments) {
    const perStyle = styleId ? assignments.perStyle?.[styleId]?.[part] : undefined
    const chosen = perStyle ?? assignments.defaults[part]
    if (chosen) return { source: 'custom', id: chosen }
  }
  return { source: 'builtin', voice: registryVoice }
}
