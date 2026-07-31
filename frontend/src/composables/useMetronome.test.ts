/*
 * GenreGrid — a style-based MIDI generator.
 * Copyright (C) 2026 Tw Dover
 *
 * This program is free software: you can redistribute it and/or modify it under
 * the terms of the GNU General Public License v3 or (at your option) any later
 * version. Distributed WITHOUT ANY WARRANTY. See <https://www.gnu.org/licenses/>.
 */
import { describe, it, expect } from 'vitest'
import { isDownbeat, clickInterval, beatIndexAtTicks, countInDurationSec } from './useMetronome'

describe('useMetronome — meter math', () => {
  it('isDownbeat accents the first beat of each bar', () => {
    expect([0, 1, 2, 3].map(b => isDownbeat(b, 4))).toEqual([true, false, false, false])
    expect(isDownbeat(4, 4)).toBe(true)   // top of the next bar
    expect(isDownbeat(6, 7)).toBe(false)  // last beat of a 7/8 bar
    expect(isDownbeat(7, 7)).toBe(true)   // downbeat of the next 7/8 bar
    expect(isDownbeat(-1, 4)).toBe(false) // guards negative (pre-roll) beats
  })

  it('clickInterval is the beat unit as a Tone note value', () => {
    expect(clickInterval(4)).toBe('4n')   // quarter-note beats (x/4)
    expect(clickInterval(8)).toBe('8n')   // eighth-note beats (x/8)
    expect(clickInterval(0)).toBe('4n')   // defaults
  })

  it('beatIndexAtTicks maps ticks to the beat index for the denominator', () => {
    const ppq = 480
    // /4: a beat is one quarter = PPQ ticks
    expect(beatIndexAtTicks(0, ppq, 4)).toBe(0)
    expect(beatIndexAtTicks(480, ppq, 4)).toBe(1)
    expect(beatIndexAtTicks(1920, ppq, 4)).toBe(4)   // bar 2 downbeat in 4/4
    // /8: a beat is one eighth = PPQ/2 ticks
    expect(beatIndexAtTicks(240, ppq, 8)).toBe(1)
    expect(beatIndexAtTicks(1680, ppq, 8)).toBe(7)   // last eighth of a 7/8 bar
  })

  it('countInDurationSec accounts for bars, beats, meter, and tempo', () => {
    // 1 bar of 4/4 at 120 BPM = 4 beats × 0.5s = 2s
    expect(countInDurationSec(1, 4, 4, 120)).toBeCloseTo(2)
    // 2 bars of 4/4 at 120 = 4s
    expect(countInDurationSec(2, 4, 4, 120)).toBeCloseTo(4)
    // 1 bar of 7/8 at 120: a beat (eighth) = 0.25s → 7 × 0.25 = 1.75s
    expect(countInDurationSec(1, 7, 8, 120)).toBeCloseTo(1.75)
    expect(countInDurationSec(0, 4, 4, 120)).toBe(0)   // off
  })
})
