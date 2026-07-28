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
import { describe, it, expect, vi } from 'vitest'
import { makeHybridKit, type KitSamplers } from './customDrumKit'
import { KIT_ROOT } from './customInstruments'
import type { SynthKit } from './synthDrums'
import type { LayeredSampler } from './layeredSampler'

// makeHybridKit only routes triggers, so it can be exercised with stand-ins —
// no AudioContext, no Tone nodes.

function fakeSynth(): SynthKit & { calls: Array<[number, number, number]> } {
  const calls: Array<[number, number, number]> = []
  return {
    calls,
    trigger: (pitch, velocity, time) => { calls.push([pitch, velocity, time]) },
    nodes: [],
  }
}

function fakeSampler() {
  return { triggerAttack: vi.fn() } as unknown as LayeredSampler & { triggerAttack: ReturnType<typeof vi.fn> }
}

describe('makeHybridKit', () => {
  it('returns the synth kit untouched when nothing is mapped', () => {
    const synth = fakeSynth()
    expect(makeHybridKit(synth, new Map())).toBe(synth)
  })

  it('plays the user sample for a mapped piece, at the kit root', () => {
    const synth = fakeSynth()
    const kick = fakeSampler()
    const samplers: KitSamplers = new Map([[36, kick]])

    makeHybridKit(synth, samplers).trigger(36, 0.8, 1.5)

    expect(kick.triggerAttack).toHaveBeenCalledWith(KIT_ROOT, 1.5, 0.8)
    // The synth must NOT also fire, or every mapped hit would double.
    expect(synth.calls).toEqual([])
  })

  it('falls through to the synth for pieces the kit does not cover', () => {
    const synth = fakeSynth()
    const kick = fakeSampler()

    const kit = makeHybridKit(synth, new Map([[36, kick]]))
    kit.trigger(38, 0.6, 2)     // snare — not in the map
    kit.trigger(42, 0.4, 2.25)  // closed hat — not in the map

    expect(synth.calls).toEqual([[38, 0.6, 2], [42, 0.4, 2.25]])
    expect(kick.triggerAttack).not.toHaveBeenCalled()
  })

  it('mixes mapped and unmapped pieces in one pattern', () => {
    const synth = fakeSynth()
    const kick = fakeSampler()
    const kit = makeHybridKit(synth, new Map([[36, kick]]))

    kit.trigger(36, 1, 0)
    kit.trigger(38, 1, 0.5)
    kit.trigger(36, 0.5, 1)

    expect(kick.triggerAttack).toHaveBeenCalledTimes(2)
    expect(synth.calls).toEqual([[38, 1, 0.5]])
  })

  it('keeps the synth kit nodes for disposal, not the samplers', () => {
    // The samplers are cached per instrument and outlive one play session; tearing
    // them down with the kit would dispose an instrument still in the cache.
    const synth = fakeSynth()
    const hybrid = makeHybridKit(synth, new Map([[36, fakeSampler()]]))
    expect(hybrid.nodes).toBe(synth.nodes)
  })
})
