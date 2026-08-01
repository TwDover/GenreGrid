/*
 * GenreGrid — a style-based MIDI generator.
 * Copyright (C) 2026 Tw Dover
 *
 * This program is free software: you can redistribute it and/or modify it under
 * the terms of the GNU General Public License v3 or (at your option) any later
 * version. Distributed WITHOUT ANY WARRANTY. See <https://www.gnu.org/licenses/>.
 */
// Pure geometry + snapping for piano-roll note editing. Kept out of PianoRoll.vue
// so the canvas↔note math is unit-testable without a DOM. The forward transform
// (note → pixels) lives in PianoRoll's `noteRect`; these are its inverses plus the
// grid snap the keyboard-nudge already uses (0.25 beat = a 16th note).
import type { ParsedNote } from '../composables/useMidiPlayer'

/** Grid unit in seconds for a given tempo (16th note by default). */
export function gridSeconds(secondsPerBeat: number, division = 0.25): number {
  return division * secondsPerBeat
}

/** Snap a time (seconds) to the nearest grid line, never negative. */
export function snapTime(timeSec: number, secondsPerBeat: number, division = 0.25): number {
  const g = gridSeconds(secondsPerBeat, division)
  if (g <= 0) return Math.max(0, timeSec)
  return Math.max(0, Math.round(timeSec / g) * g)
}

/** Canvas x (buffer px) → time in seconds, clamped to the visible file. */
export function timeAtX(px: number, width: number, durationSec: number): number {
  if (width <= 0) return 0
  return Math.max(0, Math.min(durationSec, (px / width) * durationSec))
}

/** Canvas y (buffer px) → MIDI pitch, the exact inverse of PianoRoll's
 *  `y = h - ((midi - minP + 1) / pitchRange) * h`. Rounded to a semitone,
 *  clamped to the MIDI range. */
export function pitchAtY(py: number, height: number, minPitch: number, pitchRange: number): number {
  if (height <= 0 || pitchRange <= 0) return minPitch
  const midi = minPitch - 1 + ((height - py) / height) * pitchRange
  return Math.max(0, Math.min(127, Math.round(midi)))
}

/** True when a pointer x sits in a note's right-edge grab zone (for resizing). The zone
 *  is the rightmost `edgePx` pixels but never more than half the note, so a very short
 *  note doesn't become all-edge; a small overshoot past the end still grabs. */
export function nearRightEdge(px: number, noteX: number, noteW: number, edgePx = 6): boolean {
  const zone = Math.min(edgePx, noteW * 0.5)
  return px >= noteX + noteW - zone && px <= noteX + noteW + edgePx
}

/** New duration for a note whose right edge is dragged to `pointerSec`. The start stays
 *  put; the end snaps to the grid; duration never drops below one grid unit. `division`
 *  is the snap grid (0.25 = a 16th note, the default the inline roll uses). */
export function resizedDuration(startSec: number, pointerSec: number, secondsPerBeat: number,
                                division = 0.25): number {
  const g = gridSeconds(secondsPerBeat, division)
  const end = snapTime(pointerSec, secondsPerBeat, division)
  return Math.max(g, end - startSec)
}

/**
 * Build a new melodic note from a drag: press position → release position. Start and
 * end snap to the grid; duration is at least one grid unit so a plain click still makes
 * an audible note. Dragging right-to-left is fine (ends are ordered here).
 */
export function buildInsertedNote(
  aSec: number,
  bSec: number,
  midi: number,
  secondsPerBeat: number,
  velocity = 0.7,
  division = 0.25,
  isPercussion = false,
): ParsedNote {
  const g = gridSeconds(secondsPerBeat, division)
  const start = snapTime(Math.min(aSec, bSec), secondsPerBeat, division)
  const endSnapped = snapTime(Math.max(aSec, bSec), secondsPerBeat, division)
  const duration = Math.max(g, endSnapped - start)
  return {
    midi: Math.max(0, Math.min(127, Math.round(midi))),
    time: start,
    duration,
    velocity: Math.max(0.01, Math.min(1, velocity)),
    isPercussion,
  }
}

// ── Zoomable-editor viewport ──────────────────────────────────────────────────
// The modal editor (PianoRollEditor.vue) draws at an explicit scale + scroll rather
// than fitting the whole file to the card. These transforms are the single source of
// truth for that surface's note↔pixel math (kept here so they're unit-tested without a
// DOM). Coordinates are canvas-buffer pixels; the note grid begins at (gutterW, rulerH),
// and content scrolls under it by (scrollX, scrollY).
export interface RollViewport {
  pxPerBeat: number       // horizontal zoom
  pxPerSemitone: number   // vertical zoom
  scrollX: number         // content px scrolled left of the grid origin
  scrollY: number         // content px scrolled above the grid origin
  topPitch: number        // MIDI pitch drawn at the top grid row
  secondsPerBeat: number  // file tempo — seconds ↔ beats
  gutterW: number         // left keyboard-gutter width (px)
  rulerH: number          // top ruler height (px)
}

/** Beat number → canvas x (grid origin at gutterW, minus horizontal scroll). */
export function beatToX(beat: number, vp: RollViewport): number {
  return vp.gutterW - vp.scrollX + beat * vp.pxPerBeat
}

/** Canvas x → beat number (inverse of beatToX), clamped ≥ 0. */
export function xToBeat(px: number, vp: RollViewport): number {
  if (vp.pxPerBeat <= 0) return 0
  return Math.max(0, (px - vp.gutterW + vp.scrollX) / vp.pxPerBeat)
}

/** Seconds → canvas x. */
export function timeToX(sec: number, vp: RollViewport): number {
  return beatToX(vp.secondsPerBeat > 0 ? sec / vp.secondsPerBeat : 0, vp)
}

/** Canvas x → seconds, clamped ≥ 0. */
export function xToTime(px: number, vp: RollViewport): number {
  return xToBeat(px, vp) * vp.secondsPerBeat
}

/** MIDI pitch → canvas y (top row = topPitch; each semitone is pxPerSemitone tall). */
export function pitchToY(midi: number, vp: RollViewport): number {
  return vp.rulerH - vp.scrollY + (vp.topPitch - midi) * vp.pxPerSemitone
}

/** Canvas y → MIDI pitch (inverse of pitchToY), rounded + clamped to the MIDI range. */
export function yToPitch(py: number, vp: RollViewport): number {
  if (vp.pxPerSemitone <= 0) return vp.topPitch
  const midi = vp.topPitch - (py - vp.rulerH + vp.scrollY) / vp.pxPerSemitone
  return Math.max(0, Math.min(127, Math.round(midi)))
}

/** Pixel rect of a note in the zoomable editor — the forward transform the editor
 *  both draws and hit-tests against (mirrors PianoRoll's `noteRect`). A percussion
 *  note is a fixed-height diamond-ish bar on its pitch row. */
export function noteRectZoom(note: ParsedNote, vp: RollViewport): { x: number; y: number; w: number; h: number } {
  const x = timeToX(note.time, vp)
  const w = Math.max(2, (note.duration / (vp.secondsPerBeat || 1)) * vp.pxPerBeat)
  const y = pitchToY(note.midi, vp)
  return { x, y, w, h: Math.max(3, vp.pxPerSemitone - 1) }
}

const _NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

/** MIDI number → scientific pitch name, e.g. 60 → "C4", 61 → "C#4". */
export function midiToNoteName(midi: number): string {
  const pc = ((midi % 12) + 12) % 12
  const octave = Math.floor(midi / 12) - 1
  return `${_NOTE_NAMES[pc]}${octave}`
}

/** True for the five black keys of the octave — used to shade the keyboard gutter. */
export function isBlackKey(midi: number): boolean {
  return [1, 3, 6, 8, 10].includes(((midi % 12) + 12) % 12)
}

// GM percussion pitch → short piece name (the KICK/SNARE/HAT/… voice map in
// synthDrums.ts, extended across the full GM range). Short so it fits the editor's
// 54px keyboard gutter; falls back to the raw pitch for anything unmapped.
const _DRUM_NAMES: Record<number, string> = {
  35: 'Kick', 36: 'Kick', 37: 'Rim', 38: 'Snare', 39: 'Clap', 40: 'Snare',
  41: 'Tom', 42: 'HH', 43: 'Tom', 44: 'HH', 45: 'Tom', 46: 'Open HH',
  47: 'Tom', 48: 'Tom', 49: 'Crash', 50: 'Tom', 51: 'Ride', 52: 'Crash',
  53: 'Ride', 54: 'Tamb', 55: 'Crash', 56: 'Cowbell', 57: 'Crash', 58: 'Vibra',
  59: 'Ride', 60: 'Bongo', 61: 'Bongo', 62: 'Conga', 63: 'Conga', 64: 'Conga',
  65: 'Timbale', 66: 'Timbale', 67: 'Agogo', 68: 'Agogo', 69: 'Cabasa',
  70: 'Maracas', 71: 'Whistle', 72: 'Whistle', 73: 'Guiro', 74: 'Guiro',
  75: 'Claves', 76: 'Woodblk', 77: 'Woodblk', 78: 'Cuica', 79: 'Cuica',
  80: 'Triangle', 81: 'Triangle',
}
/** GM drum pitch → a short piece label for the drum-lane gutter (e.g. 36 → "Kick"). */
export function drumPieceName(midi: number): string {
  return _DRUM_NAMES[midi] ?? `#${midi}`
}

// GM percussion occupies MIDI notes 35–81 (Acoustic Bass Drum … Open Triangle).
// Anything outside maps to no kit piece — a keyboard played as drums would send
// chromatic notes that just clutter the roll with unused lanes.
export const GM_DRUM_MIN = 35
export const GM_DRUM_MAX = 81
/** True when a pitch is within the GM percussion range (a real drum-kit note). */
export function isDrumPitch(midi: number): boolean {
  return midi >= GM_DRUM_MIN && midi <= GM_DRUM_MAX
}

/** Velocity lane y (canvas px) → velocity 0..1. The lane fills bottom-up: a hit at the
 *  lane's bottom edge is ~0, the top edge ~1. Clamped to an audible floor. */
export function velocityFromLaneY(py: number, laneTop: number, laneH: number): number {
  if (laneH <= 0) return 0.7
  const v = (laneTop + laneH - py) / laneH
  return Math.max(0.02, Math.min(1, v))
}

/** Snap a drag delta (seconds) to the grid — used when moving a group of notes so they
 *  shift by whole grid steps and stay aligned. */
export function snapDelta(deltaSec: number, secondsPerBeat: number, division = 0.25): number {
  const g = gridSeconds(secondsPerBeat, division)
  if (g <= 0) return deltaSec
  return Math.round(deltaSec / g) * g
}

/** True when a pointer x is within `zone` px of a loop-boundary flag at `flagX` — lets
 *  each loop edge be grabbed and dragged independently in the ruler. */
export function nearLoopFlag(px: number, flagX: number, zone = 6): boolean {
  return Math.abs(px - flagX) <= zone
}

/**
 * Make an edited note list safe to schedule with Tone.js. Tone requires each successive
 * trigger of the same audio source to start strictly *after* the previous one, so two
 * notes that share a start time throw "Start time must be strictly greater than previous
 * start time". Editing lets you stack notes on the same cell (or move one onto another),
 * so nudge any colliding start forward by `minGap`. Grouped per pitch for polyphonic parts;
 * `mono` (bass) collapses the whole part to one strictly-increasing timeline since a mono
 * synth can only sound one note at a time. Returns copies, sorted within each group; the
 * saved stem is unaffected (the backend trims overlaps on write).
 */
export function sanitizeNotesForPlayback(notes: ParsedNote[], mono = false, minGap = 0.03): ParsedNote[] {
  const groups = new Map<number, ParsedNote[]>()
  for (const n of notes) {
    const key = mono ? 0 : n.midi
    const g = groups.get(key)
    if (g) g.push({ ...n })
    else groups.set(key, [{ ...n }])
  }
  const out: ParsedNote[] = []
  for (const group of groups.values()) {
    group.sort((a, b) => a.time - b.time)
    let prev = -Infinity
    for (const n of group) {
      if (n.time <= prev) n.time = prev + minGap
      prev = n.time
      out.push(n)
    }
  }
  return out
}

/** Axis-aligned rectangle overlap (used to hit-test notes against a marquee box). */
export function rectsOverlap(
  ax: number, ay: number, aw: number, ah: number,
  bx: number, by: number, bw: number, bh: number,
): boolean {
  return ax < bx + bw && ax + aw > bx && ay < by + bh && ay + ah > by
}
