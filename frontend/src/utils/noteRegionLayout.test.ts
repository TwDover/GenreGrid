/*
 * GenreGrid — a style-based MIDI generator.
 * Copyright (C) 2026 Tw Dover
 *
 * This program is free software: you can redistribute it and/or modify it under
 * the terms of the GNU General Public License v3 or (at your option) any later
 * version. Distributed WITHOUT ANY WARRANTY. See <https://www.gnu.org/licenses/>.
 */
import { describe, it, expect } from 'vitest'
import { barToPercent, regionRect, pxDeltaToBars, clampNewStartBar, regionsOverlap } from './noteRegionLayout'

describe('barToPercent', () => {
  it('scales linearly against the total bar count', () => {
    expect(barToPercent(0, 40)).toBe(0)
    expect(barToPercent(20, 40)).toBe(50)
    expect(barToPercent(40, 40)).toBe(100)
  })

  it('clamps to 0..100 and guards a zero total', () => {
    expect(barToPercent(-5, 40)).toBe(0)
    expect(barToPercent(80, 40)).toBe(100)
    expect(barToPercent(4, 0)).toBe(0)
  })
})

describe('regionRect', () => {
  it('spans start_bar..start_bar+bars for a single (non-looped) region', () => {
    const r = regionRect(4, 8, 1, 40)
    expect(r.leftPct).toBe(10)
    expect(r.widthPct).toBe(20)
  })

  it('widens to cover every loop repeat', () => {
    const r = regionRect(4, 8, 3, 40)
    expect(r.leftPct).toBe(10)
    expect(r.widthPct).toBeCloseTo(60, 5)   // 8*3 = 24 bars of 40 = 60%
  })

  it('never returns a negative width', () => {
    const r = regionRect(100, 8, 1, 40)   // start already past the end
    expect(r.widthPct).toBe(0)
  })
})

describe('pxDeltaToBars', () => {
  it('rounds a pixel delta to the nearest whole bar', () => {
    const pxPerBar = 20
    expect(pxDeltaToBars(45, pxPerBar)).toBe(2)   // 2.25 → 2
    expect(pxDeltaToBars(-55, pxPerBar)).toBe(-3) // -2.75 → -3
    expect(pxDeltaToBars(0, pxPerBar)).toBe(0)
  })

  it('guards a zero/negative px-per-bar', () => {
    expect(pxDeltaToBars(50, 0)).toBe(0)
  })
})

describe('clampNewStartBar', () => {
  it('leaves an in-bounds move untouched', () => {
    expect(clampNewStartBar(10, 4, 1, 40)).toBe(10)
  })

  it('clamps so the full looped span never runs past the end', () => {
    expect(clampNewStartBar(39, 4, 1, 40)).toBe(36)   // 36+4=40, the last legal spot
    expect(clampNewStartBar(39, 4, 3, 40)).toBe(28)   // 28+12=40
  })

  it('never returns a negative bar', () => {
    expect(clampNewStartBar(-5, 4, 1, 40)).toBe(0)
  })
})

describe('regionsOverlap', () => {
  it('detects an overlap between two single-loop windows', () => {
    const a = { start_bar: 2, bars: 4, loop_count: 1 }   // bars 2..6
    const b = { start_bar: 5, bars: 4, loop_count: 1 }   // bars 5..9
    expect(regionsOverlap(a, b)).toBe(true)
  })

  it('reports no overlap for adjacent, non-overlapping windows', () => {
    const a = { start_bar: 0, bars: 4, loop_count: 1 }   // bars 0..4
    const b = { start_bar: 4, bars: 4, loop_count: 1 }   // bars 4..8
    expect(regionsOverlap(a, b)).toBe(false)
  })

  it('accounts for loop_count widening the effective window', () => {
    const a = { start_bar: 0, bars: 2, loop_count: 3 }   // bars 0..6
    const b = { start_bar: 5, bars: 2, loop_count: 1 }   // bars 5..7
    expect(regionsOverlap(a, b)).toBe(true)
  })
})
