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
import {
  normalizeLayers,
  selectLayerIndex,
  roundRobinWidth,
  urlsForRoundRobin,
  type VelocityLayer,
} from './layeredSampler'

// The LayeredSampler class needs a real AudioContext (Tone.Sampler), so these
// exercise the pure selection/loading logic that decides which sample plays.
describe('LayeredSampler layer selection', () => {
  const layers: VelocityLayer[] = [
    { maxVelocity: 0.4, urls: { C4: 'soft/C4.mp3' } },
    { maxVelocity: 0.75, urls: { C4: 'mid/C4.mp3' } },
    { maxVelocity: 1, urls: { C4: 'hard/C4.mp3' } },
  ]

  it('picks the lowest layer whose ceiling covers the velocity', () => {
    expect(selectLayerIndex(layers, 0.1)).toBe(0)
    expect(selectLayerIndex(layers, 0.4)).toBe(0)  // inclusive upper bound
    expect(selectLayerIndex(layers, 0.41)).toBe(1)
    expect(selectLayerIndex(layers, 0.75)).toBe(1)
    expect(selectLayerIndex(layers, 0.76)).toBe(2)
    expect(selectLayerIndex(layers, 1)).toBe(2)
  })

  it('clamps out-of-range velocity to the top layer', () => {
    expect(selectLayerIndex(layers, 1.5)).toBe(2)
    expect(selectLayerIndex(layers, 99)).toBe(2)
  })
})

describe('normalizeLayers', () => {
  it('produces a single full-range layer from a legacy map', () => {
    const out = normalizeLayers({ legacyUrls: { C4: 'C4.mp3', E4: 'E4.mp3' } })
    expect(out).toHaveLength(1)
    expect(out[0].maxVelocity).toBe(1)
    expect(out[0].urls).toEqual({ C4: 'C4.mp3', E4: 'E4.mp3' })
  })

  it('sorts manifest layers ascending and forces the top ceiling to 1', () => {
    const out = normalizeLayers({
      manifest: {
        layers: [
          { maxVelocity: 0.9, urls: { C4: 'hard/C4.mp3' } }, // authored below 1 …
          { maxVelocity: 0.3, urls: { C4: 'soft/C4.mp3' } },
        ],
      },
    })
    expect(out.map(l => l.maxVelocity)).toEqual([0.3, 1]) // sorted + top clamped to 1
    expect(out[0].urls.C4).toBe('soft/C4.mp3')
  })

  it('prefers the manifest when both are supplied', () => {
    const out = normalizeLayers({
      manifest: { layers: [{ maxVelocity: 1, urls: { C4: 'a.mp3' } }] },
      legacyUrls: { C4: 'legacy.mp3' },
    })
    expect(out[0].urls.C4).toBe('a.mp3')
  })
})

describe('round-robin expansion', () => {
  it('reports the widest note as the round-robin width', () => {
    const layer: VelocityLayer = { maxVelocity: 1, urls: { C4: ['a.mp3', 'b.mp3'], E4: 'e.mp3' } }
    expect(roundRobinWidth(layer)).toBe(2)
  })

  it('single-file notes have width 1', () => {
    expect(roundRobinWidth({ maxVelocity: 1, urls: { C4: 'c.mp3', E4: 'e.mp3' } })).toBe(1)
  })

  it('maps each round-robin slot, reusing the last alternate for shorter notes', () => {
    const layer: VelocityLayer = { maxVelocity: 1, urls: { C4: ['c0.mp3', 'c1.mp3'], E4: 'e.mp3' } }
    expect(urlsForRoundRobin(layer, 0)).toEqual({ C4: 'c0.mp3', E4: 'e.mp3' })
    // E4 has only one alternate, so slot 1 reuses it; C4 advances.
    expect(urlsForRoundRobin(layer, 1)).toEqual({ C4: 'c1.mp3', E4: 'e.mp3' })
  })
})
