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
import { useDrumKitPatches, builtinKitOptions } from './useDrumKitPatches'
import { builtinKitPatch } from '../soundfonts/synthDrums'

// The store is a module singleton backed by localStorage (present in jsdom); each test
// cleans up the assignment/kits it makes so ordering doesn't matter.
const dp = useDrumKitPatches()
afterEach(() => {
  dp.assignKit(null)
  dp.assignments.value.perStyle = {}
  for (const k of [...dp.kits.value]) dp.deleteKit(k.id)
})

describe('builtinKitOptions', () => {
  it('lists all seven built-in kits by slug + label', () => {
    const opts = builtinKitOptions()
    expect(opts).toHaveLength(7)
    expect(opts.find(o => o.id === 'techno')?.label).toBe('Techno')
    expect(opts.find(o => o.id === 'breakbeat')?.label).toBe('Breakbeat')
  })
})

describe('resolveKitForStyle', () => {
  it('falls back to the style\'s built-in character when nothing is assigned', () => {
    expect(dp.resolveKitForStyle('techno')).toEqual(builtinKitPatch('techno'))
    expect(dp.resolveKitForStyle('jazz')).toEqual(builtinKitPatch('acoustic'))
    expect(dp.resolveKitForStyle(undefined)).toEqual(builtinKitPatch('acoustic'))
  })

  it('resolves a global built-in-slug assignment over every style', () => {
    dp.assignKit('vintage')
    expect(dp.resolveKitForStyle('techno')).toEqual(builtinKitPatch('vintage'))
    expect(dp.resolveKitForStyle(undefined)).toEqual(builtinKitPatch('vintage'))
  })

  it('resolves a saved-kit assignment', () => {
    const custom = { ...builtinKitPatch('acoustic'), kickDecay: 0.99 }
    const saved = dp.saveKit('My Kit', custom)
    dp.assignKit(saved.id)
    expect(dp.resolveKitForStyle(undefined)?.kickDecay).toBe(0.99)
  })

  it('falls back to the style default when the assigned id no longer exists', () => {
    dp.assignKit('no-such-id')
    expect(dp.resolveKitForStyle('techno')).toEqual(builtinKitPatch('techno'))
  })

  it('a per-style assignment only affects that style', () => {
    dp.assignKit('digital', 'reggaeton')
    expect(dp.resolveKitForStyle('reggaeton')).toEqual(builtinKitPatch('digital'))
    expect(dp.resolveKitForStyle('jazz')).toEqual(builtinKitPatch('acoustic'))
  })
})

describe('save / delete', () => {
  it('re-saving the same name updates the kit in place rather than duplicating', () => {
    const first = dp.saveKit('Snappy', builtinKitPatch('punchy'))
    const second = dp.saveKit('Snappy', { ...builtinKitPatch('punchy'), snareToneMix: 0.9 })
    expect(second.id).toBe(first.id)
    expect(dp.kits.value.filter(k => k.name === 'Snappy')).toHaveLength(1)
    expect(dp.getKit(first.id)?.patch.snareToneMix).toBe(0.9)
  })

  it('deleting an assigned kit clears the assignment so it falls back to the default', () => {
    const saved = dp.saveKit('Gone Soon', builtinKitPatch('lofi'))
    dp.assignKit(saved.id)
    expect(dp.assignedId(undefined, 'all')).toBe(saved.id)
    dp.deleteKit(saved.id)
    expect(dp.assignedId(undefined, 'all')).toBeUndefined()
    expect(dp.resolveKitForStyle(undefined)).toEqual(builtinKitPatch('acoustic'))
  })
})
