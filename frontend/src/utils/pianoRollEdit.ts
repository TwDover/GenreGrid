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
 *  put; the end snaps to the grid; duration never drops below one grid unit. */
export function resizedDuration(startSec: number, pointerSec: number, secondsPerBeat: number): number {
  const g = gridSeconds(secondsPerBeat)
  const end = snapTime(pointerSec, secondsPerBeat)
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
): ParsedNote {
  const g = gridSeconds(secondsPerBeat)
  const start = snapTime(Math.min(aSec, bSec), secondsPerBeat)
  const endSnapped = snapTime(Math.max(aSec, bSec), secondsPerBeat)
  const duration = Math.max(g, endSnapped - start)
  return {
    midi: Math.max(0, Math.min(127, Math.round(midi))),
    time: start,
    duration,
    velocity: Math.max(0.01, Math.min(1, velocity)),
    isPercussion: false,
  }
}
