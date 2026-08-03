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
import { saturationCurve, saturationCurveSamples, resolveToneValues, TONE_PRESETS } from './partTone'

// The per-part tone preset's saturation stage. The WaveShaper node itself needs a
// real AudioContext, so this tests the pure transfer function — same pattern as
// loader.ts's softClipCurve (see masterLimiter.test.ts).
describe('saturationCurve', () => {
  it('is perfectly transparent at drive=0', () => {
    for (const x of [-1, -0.5, 0, 0.3, 0.9, 1]) {
      expect(saturationCurve(x, 0)).toBeCloseTo(x, 12)
    }
  })

  it('is an odd function (symmetric for positive/negative signals)', () => {
    for (const drive of [0.5, 2.5, 5]) {
      for (const x of [0.1, 0.4, 0.8, 1]) {
        expect(saturationCurve(-x, drive)).toBeCloseTo(-saturationCurve(x, drive), 12)
      }
    }
  })

  it('stays within [-1, 1] for in-range input', () => {
    for (const drive of [0.5, 2.5, 5]) {
      for (let x = -1; x <= 1; x += 0.1) {
        const y = saturationCurve(x, drive)
        expect(y).toBeGreaterThanOrEqual(-1)
        expect(y).toBeLessThanOrEqual(1)
      }
    }
  })

  it('reaches unity at the edges regardless of drive (normalized by tanh(k))', () => {
    for (const drive of [0.5, 2.5, 5]) {
      expect(saturationCurve(1, drive)).toBeCloseTo(1, 6)
      expect(saturationCurve(-1, drive)).toBeCloseTo(-1, 6)
    }
  })

  it('is monotonic (never folds back on itself)', () => {
    for (const drive of [0.5, 2.5, 5]) {
      let prev = saturationCurve(-1, drive)
      for (let x = -0.99; x <= 1; x += 0.01) {
        const y = saturationCurve(x, drive)
        expect(y).toBeGreaterThan(prev)
        prev = y
      }
    }
  })
})

describe('saturationCurveSamples', () => {
  it('samples the curve across the requested length, matching saturationCurve directly', () => {
    const length = 8
    const samples = saturationCurveSamples(2.5, length)
    expect(samples.length).toBe(length)
    for (let i = 0; i < length; i++) {
      const x = (i / (length - 1)) * 2 - 1
      expect(samples[i]).toBeCloseTo(saturationCurve(x, 2.5), 6)
    }
  })
})

describe('resolveToneValues', () => {
  it('neutral is always identity, regardless of amount', () => {
    expect(resolveToneValues({ preset: 'neutral', amount: 1 })).toEqual({ lowShelfDb: 0, highShelfDb: 0, drive: 0 })
    expect(resolveToneValues({ preset: 'neutral', amount: 0.3 })).toEqual({ lowShelfDb: 0, highShelfDb: 0, drive: 0 })
  })

  it('scales a tuned preset linearly by amount', () => {
    const full = resolveToneValues({ preset: 'warm', amount: 1 })
    expect(full).toEqual({
      lowShelfDb: TONE_PRESETS.warm.lowShelfDb,
      highShelfDb: TONE_PRESETS.warm.highShelfDb,
      drive: TONE_PRESETS.warm.drive,
    })
    const half = resolveToneValues({ preset: 'warm', amount: 0.5 })
    expect(half.lowShelfDb).toBeCloseTo(TONE_PRESETS.warm.lowShelfDb / 2, 6)
    expect(half.highShelfDb).toBeCloseTo(TONE_PRESETS.warm.highShelfDb / 2, 6)
  })

  it('clamps amount to [0, 1]', () => {
    const over = resolveToneValues({ preset: 'saturated', amount: 5 })
    expect(over.drive).toBeCloseTo(TONE_PRESETS.saturated.drive, 6)
    const under = resolveToneValues({ preset: 'saturated', amount: -5 })
    expect(under.drive).toBe(0)
  })
})
