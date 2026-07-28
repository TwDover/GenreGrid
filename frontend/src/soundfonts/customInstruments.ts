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
 *  addressed by the manifest's file names relative to the instrument's base URL).
 *
 *  `kind` is not cosmetic: it selects which of the two mapping shapes applies.
 *  'melodic' and 'bass' are **chromatic** — one manifest whose zones are pitched
 *  and stretched across the keyboard. 'drums' is a **kit** — a fixed pitch → one-shot
 *  map where nothing is ever pitch-shifted, because stretching a kick into a ride is
 *  not a thing anyone wants. The two cannot share a structure, which is why a kit
 *  lives in `kit` and leaves `manifest` empty. */
export interface CustomInstrument {
  id: string
  name: string
  kind: 'melodic' | 'bass' | 'drums'
  manifest: LayeredSamplerManifest
  /** Present only for kind 'drums'. Keyed by GM percussion pitch. */
  kit?: DrumKitMap
  createdAt: number
}

/** Every kit sample is stored as a single-zone manifest rooted at this note, so the
 *  sampler that plays it has exactly one zone and can never pitch-shift between
 *  pieces. The kit player triggers this note and the piece sounds at its true pitch. */
export const KIT_ROOT = 'C4'

/** GM percussion pitch → that piece's velocity layers / round-robins, as a
 *  single-zone manifest. Pitches absent from the map fall through to the synth kit,
 *  so a half-filled kit is useful immediately. */
export type DrumKitMap = Record<number, LayeredSamplerManifest>

export interface DrumSlot {
  pitch: number
  id: string
  label: string
  /** Distinctive substrings — matched anywhere in the filename. */
  strong: string[]
  /** Short abbreviations — matched only as a whole token, so "ch" doesn't eat "chord". */
  tokens: string[]
}

// The pitches the generator actually emits, mirroring DRUM_MAP in the backend's
// core/constants.py. Order is match priority, not display order: open hat must beat
// closed hat ("hat" appears in both) and the toms must beat the bare "tom".
export const DRUM_SLOTS: readonly DrumSlot[] = [
  { pitch: 46, id: 'open_hat', label: 'Open Hat', strong: ['openhat', 'open_hat', 'open hat', 'open-hat'], tokens: ['oh', 'ohh'] },
  { pitch: 42, id: 'closed_hat', label: 'Closed Hat', strong: ['closedhat', 'closed_hat', 'closed hat', 'hihat', 'hi-hat', 'hi_hat', 'hat'], tokens: ['hh', 'ch', 'chh'] },
  { pitch: 36, id: 'kick', label: 'Kick', strong: ['kick', 'bassdrum', 'bass_drum', 'bass drum'], tokens: ['bd'] },
  { pitch: 38, id: 'snare', label: 'Snare', strong: ['snare'], tokens: ['sd', 'sn'] },
  { pitch: 39, id: 'clap', label: 'Clap', strong: ['clap', 'handclap'], tokens: ['cp'] },
  { pitch: 49, id: 'crash', label: 'Crash', strong: ['crash'], tokens: ['cr', 'cy'] },
  { pitch: 51, id: 'ride', label: 'Ride', strong: ['ride'], tokens: ['rd'] },
  { pitch: 43, id: 'tom_lo', label: 'Low Tom', strong: ['lowtom', 'low_tom', 'low tom', 'floortom', 'floor_tom', 'tom_lo', 'tomlo', 'tom3'], tokens: ['ft', 'lt'] },
  { pitch: 47, id: 'tom_mid', label: 'Mid Tom', strong: ['midtom', 'mid_tom', 'mid tom', 'tom_mid', 'tommid', 'tom2'], tokens: ['mt'] },
  { pitch: 50, id: 'tom_hi', label: 'High Tom', strong: ['hightom', 'high_tom', 'high tom', 'hitom', 'tom_hi', 'tomhi', 'tom1'], tokens: ['ht'] },
  { pitch: 60, id: 'perc1', label: 'Perc 1', strong: ['perc1', 'shaker', 'tambourine', 'tamb', 'cowbell', 'rimshot', 'rim'], tokens: [] },
  { pitch: 61, id: 'perc2', label: 'Perc 2', strong: ['perc2', 'conga', 'bongo', 'woodblock', 'clave', 'perc'], tokens: [] },
] as const

/** Per-part instrument assignments: a global default map plus optional per-style
 *  overrides. Values are custom-instrument ids.
 *
 *  A per-style value of `''` means "built-in **for this style**", which is not the
 *  same as having no entry at all (that inherits the global default). Without the
 *  distinction, picking "Built-in" for one style would silently fall through to
 *  whatever the all-styles default is. */
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

  return { manifest: { layers: groupIntoLayers(parsed, p => p.note ?? defaultRoot) }, mapped: audio.length, skipped }
}

type ParsedPath = ParsedSampleName & { path: string }

/** Group parsed files into ascending velocity layers, placing each into the zone
 *  `noteFor` picks. Files sharing a zone within a layer become round-robins. */
function groupIntoLayers(parsed: ParsedPath[], noteFor: (p: ParsedPath) => string): VelocityLayer[] {
  const byLayer = new Map<string, ParsedPath[]>()
  for (const p of parsed) {
    const key = p.layer ?? ''
    if (!byLayer.has(key)) byLayer.set(key, [])
    byLayer.get(key)!.push(p)
  }

  const layerKeys = [...byLayer.keys()].sort((a, b) => dynRank(a) - dynRank(b))
  return layerKeys.map((key, idx) => {
    // Ascending, evenly-spaced ceilings; the top layer always reaches 1.
    const maxVelocity = idx === layerKeys.length - 1 ? 1 : (idx + 1) / layerKeys.length
    const urls: Record<string, string | string[]> = {}
    for (const p of byLayer.get(key)!) {
      const note = noteFor(p)
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
}

// ── Drum kits ────────────────────────────────────────────────────────────────

/** Which kit piece a filename names, or null when nothing matches. Distinctive
 *  words are matched anywhere; two-letter abbreviations only as whole tokens, so
 *  "chord_stab.wav" isn't filed as a closed hat because it contains "ch". */
export function matchDrumSlot(path: string): DrumSlot | null {
  const base = path.split('/').pop()!.replace(AUDIO_EXT, '').toLowerCase()
  const haystack = path.toLowerCase()
  for (const slot of DRUM_SLOTS) {
    if (slot.strong.some(s => haystack.includes(s))) return slot
  }
  const tokens = base.split(/[^a-z0-9]+/).filter(Boolean)
  for (const slot of DRUM_SLOTS) {
    if (slot.tokens.some(t => tokens.includes(t))) return slot
  }
  return null
}

export interface BuildKitResult {
  kit: DrumKitMap
  mapped: number
  /** Audio files no slot claimed — the UI offers these for manual placement. */
  unmatched: string[]
  skipped: string[]
}

/**
 * Build a drum kit from dropped files by matching each filename to a GM piece.
 * Velocity-layer and round-robin hints work exactly as they do for chromatic
 * instruments (`kick/soft/01.wav`, `snare_rr2.wav`), applied per piece.
 *
 * Unmatched audio is returned rather than guessed at — a file placed on the wrong
 * drum is worse than a file the user places themselves.
 */
export function buildKit(paths: string[]): BuildKitResult {
  const audio = paths.filter(isAudioFile)
  const skipped = paths.filter(p => !isAudioFile(p))

  const bySlot = new Map<number, ParsedPath[]>()
  const unmatched: string[] = []
  for (const path of audio) {
    const slot = matchDrumSlot(path)
    if (!slot) { unmatched.push(path); continue }
    if (!bySlot.has(slot.pitch)) bySlot.set(slot.pitch, [])
    bySlot.get(slot.pitch)!.push({ path, ...parseSampleName(path) })
  }

  const kit: DrumKitMap = {}
  let mapped = 0
  for (const [pitch, files] of bySlot) {
    kit[pitch] = { layers: groupIntoLayers(files, () => KIT_ROOT) }
    mapped += files.length
  }
  return { kit, mapped, unmatched, skipped }
}

/** Put specific files on one kit piece, replacing whatever was there. Passing no
 *  paths clears the slot, which drops it back to the synth kit's version. */
export function setKitSlot(kit: DrumKitMap, pitch: number, paths: string[]): DrumKitMap {
  const next = { ...kit }
  const audio = paths.filter(isAudioFile)
  if (audio.length === 0) {
    delete next[pitch]
    return next
  }
  const parsed = audio.map(p => ({ path: p, ...parseSampleName(p) }))
  next[pitch] = { layers: groupIntoLayers(parsed, () => KIT_ROOT) }
  return next
}

/** Every file a kit references, deduplicated — used to keep stored audio in sync
 *  with the map after slot edits. */
export function kitFiles(kit: DrumKitMap): string[] {
  const out = new Set<string>()
  for (const manifest of Object.values(kit)) {
    for (const layer of manifest.layers) {
      for (const v of Object.values(layer.urls)) {
        for (const f of Array.isArray(v) ? v : [v]) out.add(f)
      }
    }
  }
  return [...out]
}

/**
 * Resolve which instrument plays a part: a user assignment wins over the registry
 * voice. Returns either a custom-instrument id (with `source: 'custom'`) or the
 * built-in registry voice (`source: 'builtin'`, possibly null → synth). Resolution
 * order: per-style override → global default → registry voice.
 *
 * An empty per-style value is an override *to* the built-in voice, so it stops the
 * global default rather than falling through to it (see InstrumentAssignments).
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
