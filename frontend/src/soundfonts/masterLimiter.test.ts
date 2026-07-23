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
import { describe, it, expect } from 'vitest'
import { softClipCurve } from './loader'

// The master soft-clip limiter's transfer curve. The WaveShaper node it feeds needs
// a real AudioContext, so these test the pure math that defines its behaviour: quiet
// signals pass untouched, loud peaks are held under the ceiling, and it never expands.
describe('softClipCurve (master limiter transfer function)', () => {
  const THRESHOLD = 0.6
  const CEILING = 0.985

  it('is perfectly transparent below the threshold', () => {
    for (const x of [0, 0.1, 0.3, 0.5, THRESHOLD]) {
      expect(softClipCurve(x)).toBeCloseTo(x, 12)
      expect(softClipCurve(-x)).toBeCloseTo(-x, 12)
    }
  })

  it('is an odd function (symmetric for positive/negative signals)', () => {
    for (const x of [0.2, 0.65, 0.8, 1, 1.5]) {
      expect(softClipCurve(-x)).toBeCloseTo(-softClipCurve(x), 12)
    }
  })

  it('holds all output at or below the ceiling, even for over-unity input', () => {
    for (const x of [0.7, 0.9, 1, 1.5, 4, 100]) {
      expect(softClipCurve(x)).toBeLessThanOrEqual(CEILING + 1e-9)
      expect(softClipCurve(x)).toBeGreaterThan(THRESHOLD) // still audibly present
    }
  })

  it('reaches the ceiling exactly at 0 dBFS and clamps beyond it', () => {
    expect(softClipCurve(1)).toBeCloseTo(CEILING, 6)
    // Web Audio clamps a WaveShaper's input to [-1, 1]; the curve must be flat past it.
    expect(softClipCurve(2)).toBeCloseTo(CEILING, 6)
    expect(softClipCurve(10)).toBeCloseTo(CEILING, 6)
  })

  it('is monotonic and never expands (0 < slope ≤ 1) through the knee', () => {
    let prev = softClipCurve(0)
    for (let x = 0.001; x <= 1; x += 0.001) {
      const y = softClipCurve(x)
      const slope = (y - prev) / 0.001
      expect(y).toBeGreaterThan(prev)          // strictly increasing
      expect(slope).toBeGreaterThan(0)
      expect(slope).toBeLessThanOrEqual(1 + 1e-6) // compresses, never boosts
      prev = y
    }
  })
})
