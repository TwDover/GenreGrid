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
