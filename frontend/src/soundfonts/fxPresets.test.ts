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
import { fxFamilyFor, MELODIC_FX_PRESETS, MASTER_TRIM_DB, STYLE_TRIM_DB, trimDbForStyle, type FxFamily } from './fxPresets'

describe('fxFamilyFor', () => {
  it('prioritises pad and lo-fi over the synth buckets', () => {
    // A style can be both pad and synth (e.g. cinematic) — pad must win.
    expect(fxFamilyFor({ isPad: true, isLofi: false, isSynth: true, isMelodicSynth: false })).toBe('pad')
    expect(fxFamilyFor({ isPad: false, isLofi: true, isSynth: true, isMelodicSynth: false })).toBe('lofi')
    expect(fxFamilyFor({ isPad: false, isLofi: false, isSynth: false, isMelodicSynth: true })).toBe('melodicSynth')
    expect(fxFamilyFor({ isPad: false, isLofi: false, isSynth: true, isMelodicSynth: false })).toBe('synth')
    expect(fxFamilyFor({ isPad: false, isLofi: false, isSynth: false, isMelodicSynth: false })).toBe('default')
  })
})

describe('preset + trim tables', () => {
  const families: FxFamily[] = ['default', 'synth', 'melodicSynth', 'pad', 'lofi']

  it('defines an FX preset and a master trim for every family', () => {
    for (const f of families) {
      expect(MELODIC_FX_PRESETS[f]).toBeDefined()
      expect(MASTER_TRIM_DB[f]).toBeTypeOf('number')
    }
  })

  it('keeps every wet mix within a sane 0..1 range', () => {
    for (const f of families) {
      const p = MELODIC_FX_PRESETS[f]
      for (const wet of [p.chorus.wet, p.delay.wet, p.reverb.wet]) {
        expect(wet).toBeGreaterThanOrEqual(0)
        expect(wet).toBeLessThanOrEqual(1)
      }
      expect(p.reverb.decay).toBeGreaterThan(0)
    }
  })

  it('trims hot electronic families down and never boosts more than a little', () => {
    expect(MASTER_TRIM_DB.synth).toBeLessThan(0)          // pulled down
    expect(MASTER_TRIM_DB.default).toBe(0)                // reference level
    for (const f of families) {
      expect(MASTER_TRIM_DB[f]).toBeGreaterThanOrEqual(-6)
      expect(MASTER_TRIM_DB[f]).toBeLessThanOrEqual(3)    // guard against runaway boost into the limiter
    }
  })
})

// Roadmap 6.2 — per-style trims measured against a -14 LUFS integrated target
// (see measure-lufs.mjs and the comment above STYLE_TRIM_DB).
describe('STYLE_TRIM_DB / trimDbForStyle', () => {
  it('keeps every measured trim within a sane range', () => {
    for (const [style, db] of Object.entries(STYLE_TRIM_DB)) {
      expect(db, style).toBeGreaterThanOrEqual(-6)
      expect(db, style).toBeLessThanOrEqual(6)
    }
  })

  it('prefers the measured per-style trim over the family fallback', () => {
    expect(STYLE_TRIM_DB.trap_soul).toBeDefined()
    expect(trimDbForStyle('trap_soul', 'pad')).toBe(STYLE_TRIM_DB.trap_soul)
    // trap_soul is a PAD_STYLES member (MASTER_TRIM_DB.pad = 1.0) but its own
    // measured trim (a cut) must win, not the family default.
    expect(trimDbForStyle('trap_soul', 'pad')).not.toBe(MASTER_TRIM_DB.pad)
  })

  it('falls back to the family default for a style with no measurement', () => {
    expect(trimDbForStyle('some_brand_new_style', 'synth')).toBe(MASTER_TRIM_DB.synth)
    expect(trimDbForStyle(undefined, 'default')).toBe(MASTER_TRIM_DB.default)
  })
})
