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
import { useSynthPatches, styleKitFor, builtinPatchOptions } from './useSynthPatches'

// The store is a module singleton backed by localStorage (present in jsdom); each test
// cleans up the assignments it makes so ordering doesn't matter.
const sp = useSynthPatches()
afterEach(() => {
  for (const part of ['bass', 'pads', 'melody', 'chords', 'arpeggio', 'counter_melody'] as const) sp.assignPatch(part, null)
  sp.assignments.value.perStyle = {}
})

describe('styleKitFor', () => {
  it('returns a known style\'s suggested kit with resolved labels', () => {
    expect(styleKitFor('dark_trap')).toEqual([{ part: 'bass', label: '808 Trap (bass)' }])
  })
  it('returns [] for a style with no kit', () => {
    expect(styleKitFor('jazz')).toEqual([])
    expect(styleKitFor(undefined)).toEqual([])
  })
})

describe('builtinPatchOptions', () => {
  it('lists built-in patches by slug + label', () => {
    const opts = builtinPatchOptions()
    expect(opts.find(o => o.id === '808_trap')?.label).toBe('808 Trap (bass)')
    expect(opts.find(o => o.id === 'reese_bass')?.label).toBe('Reese Bass')
  })
})

describe('resolvePatchForPart', () => {
  it('resolves a built-in slug assignment to that patch', () => {
    sp.assignPatch('bass', '808_trap')
    const patch = sp.resolvePatchForPart(undefined, 'bass')
    expect(patch?.voice).toBe('mono')
    expect(patch?.oscillator.type).toBe('triangle')
    expect(patch?.pitchEnvelope).toBeDefined()
  })
  it('returns null when nothing is assigned', () => {
    expect(sp.resolvePatchForPart(undefined, 'bass')).toBeNull()
  })
  it('resolves an unknown id to null (deleted patch)', () => {
    sp.assignPatch('bass', 'no-such-id')
    expect(sp.resolvePatchForPart(undefined, 'bass')).toBeNull()
  })
})

describe('applyStyleKit', () => {
  it('assigns the kit as per-style overrides', () => {
    const parts = sp.applyStyleKit('drum_and_bass')
    expect(parts).toEqual(['bass'])
    // Reese bass is a fat-saw poly voice.
    expect(sp.resolvePatchForPart('drum_and_bass', 'bass')?.oscillator.type).toBe('fatsawtooth')
    // Per-style only: another style is unaffected.
    expect(sp.resolvePatchForPart('jazz', 'bass')).toBeNull()
  })
})
