/*
 * GenreGrid — a style-based MIDI generator.
 * Copyright (C) 2026 Tw Dover
 *
 * This program is free software: you can redistribute it and/or modify it under
 * the terms of the GNU General Public License v3 or (at your option) any later
 * version. Distributed WITHOUT ANY WARRANTY. See <https://www.gnu.org/licenses/>.
 */
import { describe, it, expect } from 'vitest'
import {
  snapTime, timeAtX, pitchAtY, buildInsertedNote, gridSeconds, nearRightEdge, resizedDuration,
  beatToX, xToBeat, timeToX, xToTime, pitchToY, yToPitch, noteRectZoom,
  midiToNoteName, isBlackKey, velocityFromLaneY, snapDelta, rectsOverlap, type RollViewport,
} from './pianoRollEdit'

describe('snapTime', () => {
  it('snaps to the 16th-note grid and never goes negative', () => {
    const spb = 0.5                    // 120 BPM → grid = 0.125s
    expect(gridSeconds(spb)).toBeCloseTo(0.125)
    expect(snapTime(0.13, spb)).toBeCloseTo(0.125)
    expect(snapTime(0.19, spb)).toBeCloseTo(0.25)
    expect(snapTime(-1, spb)).toBe(0)
  })
})

describe('timeAtX', () => {
  it('maps pixels to seconds and clamps to the file', () => {
    expect(timeAtX(0, 200, 4)).toBe(0)
    expect(timeAtX(100, 200, 4)).toBeCloseTo(2)
    expect(timeAtX(500, 200, 4)).toBe(4)      // past the end clamps
    expect(timeAtX(-5, 200, 4)).toBe(0)
  })
})

describe('pitchAtY', () => {
  // Inverse of PianoRoll's noteRect y-formula. Round-trip: a note's drawn y maps back
  // to its own pitch.
  const H = 300, minP = 48, range = 36
  const yTop = (midi: number) => H - ((midi - minP + 1) / range) * H

  it('round-trips a note pitch from its drawn row', () => {
    for (const midi of [48, 60, 67, 83]) {
      expect(pitchAtY(yTop(midi), H, minP, range)).toBe(midi)
    }
  })
  it('clamps to the MIDI range', () => {
    expect(pitchAtY(-1000, H, minP, range)).toBeLessThanOrEqual(127)
    expect(pitchAtY(100000, H, minP, range)).toBeGreaterThanOrEqual(0)
  })
})

describe('buildInsertedNote', () => {
  const spb = 0.5
  it('snaps start/end and enforces a one-grid minimum duration', () => {
    const n = buildInsertedNote(0.13, 0.14, 60, spb)      // press≈release (a click)
    expect(n.time).toBeCloseTo(0.125)
    expect(n.duration).toBeCloseTo(gridSeconds(spb))       // min one grid
    expect(n.midi).toBe(60)
    expect(n.isPercussion).toBe(false)
  })
  it('sizes a dragged note and accepts right-to-left drags', () => {
    const a = buildInsertedNote(0.13, 0.62, 60, spb)       // drag right
    expect(a.time).toBeCloseTo(0.125)
    expect(a.duration).toBeCloseTo(0.5)                    // 0.625 - 0.125
    const b = buildInsertedNote(0.62, 0.13, 60, spb)       // drag left → same note
    expect(b.time).toBeCloseTo(a.time)
    expect(b.duration).toBeCloseTo(a.duration)
  })
  it('clamps velocity and pitch', () => {
    expect(buildInsertedNote(0, 0.25, 200, spb, 5).midi).toBe(127)
    expect(buildInsertedNote(0, 0.25, 60, spb, 5).velocity).toBe(1)
  })
})

describe('nearRightEdge', () => {
  it('grabs the right edge but not the body', () => {
    // note at x=100, width=40 → right end at 140
    expect(nearRightEdge(138, 100, 40)).toBe(true)    // just inside the edge
    expect(nearRightEdge(142, 100, 40)).toBe(true)    // small overshoot still grabs
    expect(nearRightEdge(120, 100, 40)).toBe(false)   // mid-body = not the edge
  })
  it('caps the zone at half the note so short notes stay selectable', () => {
    // width 4 → zone = 2; body (x<102) is not the edge
    expect(nearRightEdge(101, 100, 4)).toBe(false)
    expect(nearRightEdge(103, 100, 4)).toBe(true)
  })
})

describe('resizedDuration', () => {
  const spb = 0.5   // grid 0.125s
  it('snaps the dragged end and keeps a one-grid minimum', () => {
    expect(resizedDuration(1.0, 1.6, spb)).toBeCloseTo(0.625)   // end snaps 1.625 - 1.0
    expect(resizedDuration(1.0, 0.2, spb)).toBeCloseTo(0.125)   // dragged left → min grid
  })
})

// ── Zoomable-editor viewport (roadmap 5.1 editor) ────────────────────────────

const VP: RollViewport = {
  pxPerBeat: 48, pxPerSemitone: 15, scrollX: 120, scrollY: 30,
  topPitch: 84, secondsPerBeat: 0.5, gutterW: 54, rulerH: 26,
}

describe('viewport transforms', () => {
  it('beatToX / xToBeat round-trip across scroll + zoom', () => {
    for (const beat of [0, 1, 3.5, 16, 63.25]) {
      expect(xToBeat(beatToX(beat, VP), VP)).toBeCloseTo(beat, 6)
    }
  })
  it('timeToX / xToTime round-trip (seconds ↔ pixels)', () => {
    for (const sec of [0, 0.5, 2, 7.25]) {
      expect(xToTime(timeToX(sec, VP), VP)).toBeCloseTo(sec, 6)
    }
  })
  it('pitchToY / yToPitch round-trip and put topPitch at the top row', () => {
    // The top pitch sits at y = rulerH - scrollY (top of the grid content).
    expect(pitchToY(VP.topPitch, VP)).toBeCloseTo(VP.rulerH - VP.scrollY, 6)
    for (const midi of [48, 60, 72, 84]) {
      expect(yToPitch(pitchToY(midi, VP), VP)).toBe(midi)
    }
  })
  it('lower pitches draw further down than higher ones', () => {
    expect(pitchToY(60, VP)).toBeGreaterThan(pitchToY(72, VP))
  })
  it('noteRectZoom matches the forward transform', () => {
    const note = { midi: 72, time: 1.0, duration: 0.5, velocity: 0.7, isPercussion: false }
    const r = noteRectZoom(note, VP)
    expect(r.x).toBeCloseTo(timeToX(1.0, VP), 6)
    expect(r.y).toBeCloseTo(pitchToY(72, VP), 6)
    expect(r.w).toBeCloseTo((0.5 / 0.5) * 48, 6)   // one beat wide at 48 px/beat
  })
})

describe('note-name helpers', () => {
  it('names middle C and sharps', () => {
    expect(midiToNoteName(60)).toBe('C4')
    expect(midiToNoteName(61)).toBe('C#4')
    expect(midiToNoteName(69)).toBe('A4')
    expect(midiToNoteName(48)).toBe('C3')
  })
  it('flags the five black keys', () => {
    expect(isBlackKey(61)).toBe(true)   // C#
    expect(isBlackKey(66)).toBe(true)   // F#
    expect(isBlackKey(60)).toBe(false)  // C
    expect(isBlackKey(64)).toBe(false)  // E
  })
})

describe('snap division on the editor helpers', () => {
  const spb = 0.5   // grid: 1/16 = 0.125s, 1/8 = 0.25s
  it('buildInsertedNote honors a coarser division', () => {
    // Press near 0.3s: 1/16 snaps to 0.25, 1/8 snaps to 0.25 too; press near 0.4s differs.
    const n16 = buildInsertedNote(0.4, 0.4, 60, spb, 0.7, 0.25)   // 1/16
    const n8 = buildInsertedNote(0.4, 0.4, 60, spb, 0.7, 0.5)     // 1/8
    expect(n16.time).toBeCloseTo(0.375)   // nearest 16th
    expect(n8.time).toBeCloseTo(0.5)      // nearest 8th
    expect(n8.duration).toBeCloseTo(0.25) // one 1/8 grid unit minimum
  })
  it('resizedDuration snaps the end to the chosen division', () => {
    expect(resizedDuration(0, 0.4, spb, 0.5)).toBeCloseTo(0.5)    // end snaps to 1/8
    expect(resizedDuration(0, 0.4, spb, 0.25)).toBeCloseTo(0.375) // end snaps to 1/16
  })
  it('still defaults to a 1/16 grid when division is omitted', () => {
    expect(buildInsertedNote(0.4, 0.4, 60, spb).time).toBeCloseTo(0.375)
    expect(resizedDuration(0, 0.4, spb)).toBeCloseTo(0.375)
  })
})

// ── Velocity lane + multi-select helpers (roadmap 5.1 steps 3–4) ─────────────

describe('velocityFromLaneY', () => {
  const top = 420, h = 68   // lane spans y 420..488
  it('maps the lane top to ~1 and the bottom toward the floor', () => {
    expect(velocityFromLaneY(top, top, h)).toBeCloseTo(1)          // top edge = full
    expect(velocityFromLaneY(top + h, top, h)).toBeCloseTo(0.02)   // bottom edge = floor
    expect(velocityFromLaneY(top + h / 2, top, h)).toBeCloseTo(0.5)
  })
  it('clamps outside the lane', () => {
    expect(velocityFromLaneY(top - 50, top, h)).toBe(1)
    expect(velocityFromLaneY(top + h + 50, top, h)).toBe(0.02)
  })
})

describe('snapDelta', () => {
  const spb = 0.5   // grid 1/16 = 0.125s
  it('snaps a move delta to whole grid steps', () => {
    expect(snapDelta(0.30, spb)).toBeCloseTo(0.25)    // ~2 grid steps
    expect(snapDelta(-0.30, spb)).toBeCloseTo(-0.25)
    expect(snapDelta(0.05, spb)).toBeCloseTo(0)       // sub-grid → no move
  })
  it('honors a coarser division', () => {
    expect(snapDelta(0.30, spb, 0.5)).toBeCloseTo(0.25)   // 1/8 grid = 0.25s
  })
})

describe('rectsOverlap', () => {
  it('detects overlap and rejects disjoint boxes', () => {
    expect(rectsOverlap(0, 0, 10, 10, 5, 5, 10, 10)).toBe(true)
    expect(rectsOverlap(0, 0, 10, 10, 20, 20, 5, 5)).toBe(false)
    expect(rectsOverlap(0, 0, 10, 10, 10, 0, 5, 10)).toBe(false)   // touching edges don't overlap
  })
})
