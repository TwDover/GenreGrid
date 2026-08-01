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

// Akai APC mini mk2 wire protocol — pure data/math, no Web MIDI, no Vue.
// The mk2 surface speaks plain channel messages (no sysex needed):
//   · 8×8 pad grid   notes 0x00–0x3F, row-major from the BOTTOM-left corner
//   · track buttons  notes 0x64–0x6B (the red row under the grid)
//   · scene buttons  notes 0x70–0x77 (the green column right of the grid)
//   · shift          note 0x7A (no LED)
//   · faders         CC 0x30–0x37 (tracks 1–8) and 0x38 (master)
// Pad LEDs are set by sending a note-on BACK to the device: velocity picks a
// color from the fixed 128-entry RGB palette, and the CHANNEL picks behavior
// (0–6 = solid at rising brightness, 7–10 = pulse, 11–15 = blink at rates).
// Track/scene LEDs are single-color: velocity 0 = off, 1 = on, 2 = blink.

export const APC_GRID_SIZE = 8
export const APC_PAD_MIN = 0x00
export const APC_PAD_MAX = 0x3f
export const APC_TRACK_BTN_BASE = 0x64   // 100..107, left → right
export const APC_SCENE_BTN_BASE = 0x70   // 112..119, top → bottom on the unit
export const APC_SHIFT_NOTE = 0x7a       // 122
export const APC_FADER_CC_BASE = 0x30    // 48..55 = track faders 1..8
export const APC_MASTER_FADER_CC = 0x38  // 56

// Palette color indices (subset of the mk2's 128-color velocity palette).
export const APC_COLOR = {
  off: 0, dim: 1, gray: 2, white: 3,
  red: 5, orange: 9, yellow: 13, lime: 17, green: 21,
  cyan: 37, blue: 45, purple: 49, magenta: 53, pink: 57,
} as const
export type ApcColor = number

// Pad LED behavior → the MIDI channel the note-on is sent on.
export const APC_FX = {
  solid10: 0,   // 10% brightness — the "dim" state for unlit-but-labeled pads
  solid25: 1,
  solid50: 2,
  solid75: 4,
  solid: 6,     // 100% brightness
  pulse: 9,     // pulsing at 1/4
  blink: 14,    // blinking at 1/4
} as const

/** Grid cell (col 0..7 left→right, row 0..7 BOTTOM→top) → pad note number. */
export function cellToPad(col: number, row: number): number {
  return row * APC_GRID_SIZE + col
}
/** Pad note number → grid cell (row 0 = bottom row of the hardware). */
export function padToCell(note: number): { col: number; row: number } {
  return { col: note % APC_GRID_SIZE, row: Math.floor(note / APC_GRID_SIZE) }
}

/** Note-on that lights pad `note` in `color` with the given behavior channel. */
export function padLedMsg(note: number, color: ApcColor, fx: number = APC_FX.solid): number[] {
  return [0x90 | (fx & 0x0f), note & 0x7f, color & 0x7f]
}
/** Track/scene button LED: state 0 = off, 1 = on, 2 = blink. */
export function buttonLedMsg(note: number, state: 0 | 1 | 2): number[] {
  return [0x90, note & 0x7f, state]
}
/** Every LED off — sent on attach/detach so the surface never shows stale state. */
export function blackoutMsgs(): number[][] {
  const msgs: number[][] = []
  for (let n = APC_PAD_MIN; n <= APC_PAD_MAX; n++) msgs.push(padLedMsg(n, APC_COLOR.off, APC_FX.solid))
  for (let i = 0; i < 8; i++) msgs.push(buttonLedMsg(APC_TRACK_BTN_BASE + i, 0))
  for (let i = 0; i < 8; i++) msgs.push(buttonLedMsg(APC_SCENE_BTN_BASE + i, 0))
  return msgs
}

// ── Incoming message classification ──────────────────────────────────────────
export type ApcEvent =
  | { kind: 'pad'; col: number; row: number; on: boolean; velocity: number }
  | { kind: 'track'; index: number; on: boolean }
  | { kind: 'scene'; index: number; on: boolean }
  | { kind: 'shift'; on: boolean }
  | { kind: 'fader'; index: number; value: number }   // index 0..7 tracks, 8 master; value 0..1
  | { kind: 'other' }

/** Decode a raw message from the APC's control port into a surface event. */
export function parseApcMessage(data: ArrayLike<number>): ApcEvent {
  const cmd = (data[0] ?? 0) & 0xf0
  const d1 = data[1] ?? 0
  const d2 = data[2] ?? 0
  if (cmd === 0xb0) {
    if (d1 >= APC_FADER_CC_BASE && d1 <= APC_MASTER_FADER_CC) {
      return { kind: 'fader', index: d1 - APC_FADER_CC_BASE, value: d2 / 127 }
    }
    return { kind: 'other' }
  }
  if (cmd !== 0x90 && cmd !== 0x80) return { kind: 'other' }
  const on = cmd === 0x90 && d2 > 0
  if (d1 <= APC_PAD_MAX) return { kind: 'pad', ...padToCell(d1), on, velocity: d2 }
  if (d1 >= APC_TRACK_BTN_BASE && d1 < APC_TRACK_BTN_BASE + 8) return { kind: 'track', index: d1 - APC_TRACK_BTN_BASE, on }
  if (d1 >= APC_SCENE_BTN_BASE && d1 < APC_SCENE_BTN_BASE + 8) return { kind: 'scene', index: d1 - APC_SCENE_BTN_BASE, on }
  if (d1 === APC_SHIFT_NOTE) return { kind: 'shift', on }
  return { kind: 'other' }
}

// ── Device detection ─────────────────────────────────────────────────────────
/** True when a MIDI port name looks like an APC mini mk2. */
export function isApcMiniMk2(name: string | null | undefined): boolean {
  return /apc\s*mini\s*mk\s*2/i.test(name ?? '')
}
/** An APC mini that is NOT a mk2 (the original) — detected so the UI can say so. */
export function isApcMiniMk1(name: string | null | undefined): boolean {
  return /apc\s*mini/i.test(name ?? '') && !isApcMiniMk2(name)
}
/** Pick the surface port from candidates: the mk2 exposes a "Control" port (the
 *  surface) and a "Notes" port (a plain keyboard mode) — prefer Control. */
export function pickApcPort<T extends { name: string | null }>(ports: T[]): T | null {
  const apc = ports.filter(p => isApcMiniMk2(p.name))
  if (apc.length === 0) return null
  return apc.find(p => /control/i.test(p.name ?? '')) ?? apc[0]
}

// ── Drum rack (4×4, bottom-left quadrant, Ableton-style layout) ──────────────
// Chromatic GM pitches 36..51 laid out row-major from the bottom-left pad, which
// is exactly Ableton's drum-rack arrangement: kick / rim / snare / clap on the
// bottom row, hats and toms above, cymbals on top.
export const DRUM_RACK_SIZE = 4
export const DRUM_RACK_BASE_PITCH = 36
/** Rack cell (col/row 0..3, row 0 = bottom) → GM percussion pitch, or null off-rack. */
export function rackCellToPitch(col: number, row: number): number | null {
  if (col < 0 || col >= DRUM_RACK_SIZE || row < 0 || row >= DRUM_RACK_SIZE) return null
  return DRUM_RACK_BASE_PITCH + row * DRUM_RACK_SIZE + col
}

// ── Melodic note grid (full 8×8, rows stacked in fourths, Push-style) ────────
// When the surface targets a melodic voice, each pad is a pitch: left→right is
// chromatic, each row up adds a fourth (+5 semitones) — the guitar-ish layout
// Ableton uses, where one hand position covers more than an octave.
export const NOTE_GRID_ROW_INTERVAL = 5
/** Grid cell → MIDI pitch from `base` (bottom-left pad), or null off the ends. */
export function noteGridPitch(col: number, row: number, base: number): number | null {
  const p = base + row * NOTE_GRID_ROW_INTERVAL + col
  return p >= 0 && p <= 127 ? p : null
}
/** Default bottom-left pitch per part: bass sits two octaves under the rest. */
export function noteGridBaseFor(part: string): number {
  return part === 'bass' ? 24 : 48   // C1 / C3
}

// ── Chord grid (chords voice: pads fire diatonic triads) ─────────────────────
// Columns are scale degrees I..VII with column 8 = I an octave up; each row up
// is an octave. One pad = one in-key triad, so a chord progression is a finger
// drum pattern instead of three-note stretches.
/** The triad on the pad at (col,row): stacked scale thirds on that degree.
 *  `base` = the I-chord root pitch of row 0 (key already applied); `intervals` =
 *  the scale's 7 semitone offsets. Null when any chord tone leaves MIDI range. */
export function diatonicTriad(col: number, row: number, base: number, intervals: number[]): number[] | null {
  if (col < 0 || col >= APC_GRID_SIZE || row < 0 || row >= APC_GRID_SIZE) return null
  const degree = col % 7
  const colOctave = Math.floor(col / 7)   // column 8 wraps to the octave above
  const pitches = [0, 2, 4].map(third => {
    const d = degree + third
    return base + 12 * (row + colOctave + Math.floor(d / 7)) + (intervals[d % 7] ?? 0)
  })
  return pitches.every(p => p >= 0 && p <= 127) ? pitches : null
}

/** LED color for a GM drum pitch, grouped by kit-piece family (Ableton-ish). */
export function drumPadColor(pitch: number): ApcColor {
  if (pitch === 35 || pitch === 36) return APC_COLOR.red                       // kicks
  if (pitch === 37 || pitch === 38 || pitch === 39 || pitch === 40) return APC_COLOR.orange   // snares/rim/clap
  if (pitch === 42 || pitch === 44 || pitch === 46) return APC_COLOR.yellow    // hats
  if (pitch === 41 || pitch === 43 || pitch === 45 || pitch === 47 || pitch === 48 || pitch === 50) return APC_COLOR.blue   // toms
  if (pitch === 49 || pitch === 51 || pitch === 52 || pitch === 55 || pitch === 57 || pitch === 59) return APC_COLOR.cyan   // cymbals
  return APC_COLOR.purple                                                      // everything else (percussion)
}
