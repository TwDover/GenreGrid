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
import { describe, it, expect, afterEach } from 'vitest'
import { useMixSettings } from './useMixSettings'

// The store is a module singleton backed by localStorage (present in jsdom); each
// test resets it so ordering doesn't matter — same pattern as useSynthPatches.test.ts.
const mix = useMixSettings()
afterEach(() => {
  mix.resetMasterEQ()
  mix.partTone.value = {}
})

describe('master EQ', () => {
  it('defaults to flat', () => {
    expect(mix.masterEQ.value).toEqual({ low: 0, mid: 0, high: 0 })
  })

  it('setMasterEQBands updates and persists the value', () => {
    mix.setMasterEQBands({ low: 3, mid: -1, high: 2 })
    expect(mix.masterEQ.value).toEqual({ low: 3, mid: -1, high: 2 })
    expect(JSON.parse(localStorage.getItem('genregrid_master_eq')!)).toEqual({ low: 3, mid: -1, high: 2 })
  })

  it('resetMasterEQ returns to flat', () => {
    mix.setMasterEQBands({ low: 5, mid: 5, high: 5 })
    mix.resetMasterEQ()
    expect(mix.masterEQ.value).toEqual({ low: 0, mid: 0, high: 0 })
  })
})

describe('per-part tone', () => {
  it('resolves to neutral/full amount when unset', () => {
    expect(mix.toneForPart('bass')).toEqual({ preset: 'neutral', amount: 1 })
  })

  it('setPartTone assigns and persists one part without touching others', () => {
    mix.setPartTone('bass', { preset: 'warm', amount: 0.7 })
    expect(mix.toneForPart('bass')).toEqual({ preset: 'warm', amount: 0.7 })
    expect(mix.toneForPart('drums')).toEqual({ preset: 'neutral', amount: 1 })
    expect(JSON.parse(localStorage.getItem('genregrid_part_tone')!)).toEqual({ bass: { preset: 'warm', amount: 0.7 } })
  })
})
