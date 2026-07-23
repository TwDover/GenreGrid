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
import { describe, it, expect, beforeEach, vi } from 'vitest'

// jsdom has no real Web Audio API, so real Tone.js audio nodes can't be
// constructed here. Rather than mock the whole Web Audio surface, these fakes
// encode the two specific Tone.js behaviors that produced real bugs in this
// file (see git history / synthDrums.ts's inline comments):
//
// 1. Every voice here has a sustain:0 envelope, so Tone schedules an internal
//    auto-stop at (start + attack + decay) on every hit — retriggering the
//    same underlying voice before that point throws "the time must be
//    greater than or equal to the last scheduled time". FakeVoice enforces
//    the same minimum gap, using each instance's own attack/decay from its
//    constructor options, so a regression here fails the same way it does
//    against real Tone.js.
// 2. MetalSynth has no NoiseSynth-style triggerAttackRelease override, so it
//    takes the generic Instrument signature (note, duration, time, velocity)
//    — calling it with the NoiseSynth-shaped (duration, time, velocity) silently
//    shifts every argument by one slot instead of throwing. FakeVoice can't
//    reproduce that silent shift (real Tone.js's bug-compatible behavior
//    isn't itself something to encode), so instead each fake enforces the
//    *correct* arity for its class and throws if called with too few
//    arguments — which is exactly the shape of the original bug.
// vi.mock factories are hoisted above the whole file, so the fake classes have
// to be built inside vi.hoisted() rather than declared as normal top-level
// classes — otherwise the factory below runs before they're initialized.
const { createdInstances, FakeMembraneSynth, FakeSynth, FakeNoiseSynth, FakeMetalSynth, FakeFilter, FakeDistortion } = vi.hoisted(() => {
  const createdInstances: any[] = []

  class FakeVoice {
    static requiredArity = 4
    calls: unknown[][] = []
    frequency = { value: 0 }
    private _busyUntil = -Infinity
    private _attack: number
    private _decay: number

    constructor(opts: { envelope?: { attack?: number; decay?: number } } = {}) {
      this._attack = opts?.envelope?.attack ?? 0.001
      this._decay = opts?.envelope?.decay ?? 0
      createdInstances.push(this)
    }

    connect(_dest: unknown) { return this }

    triggerAttackRelease(...args: unknown[]) {
      const ctor = this.constructor as typeof FakeVoice
      if (args.length < ctor.requiredArity) {
        throw new Error(
          `${ctor.name}.triggerAttackRelease called with ${args.length} args ${JSON.stringify(args)}, ` +
          `expected ${ctor.requiredArity} — this is the exact shape of the MetalSynth argument-arity bug`,
        )
      }
      const time = args[ctor.requiredArity - 2]
      if (typeof time !== 'number') {
        throw new Error(`${ctor.name}.triggerAttackRelease: time argument is not a number (got ${JSON.stringify(time)})`)
      }
      if (time < this._busyUntil) {
        throw new Error(
          `${ctor.name}: retriggered at ${time}s but the previous hit's internal envelope window ` +
          `(attack ${this._attack}s + decay ${this._decay}s) doesn't close until ${this._busyUntil}s — ` +
          `mirrors Tone.js's "time must be greater than or equal to the last scheduled time"`,
        )
      }
      this._busyUntil = time + this._attack + this._decay
      this.calls.push(args)
    }
  }

  class FakeMembraneSynth extends FakeVoice { static requiredArity = 4 }
  class FakeSynth extends FakeVoice { static requiredArity = 4 }
  class FakeNoiseSynth extends FakeVoice { static requiredArity = 3 }   // has its own (duration, time, velocity) override
  class FakeMetalSynth extends FakeVoice { static requiredArity = 4 }   // no override — generic (note, duration, time, velocity)

  class FakeFilter {
    constructor(_opts?: unknown) {}
    connect(_dest: unknown) { return this }
  }
  class FakeDistortion {
    constructor(_opts?: unknown) {}
    connect(_dest: unknown) { return this }
  }

  return { createdInstances, FakeMembraneSynth, FakeSynth, FakeNoiseSynth, FakeMetalSynth, FakeFilter, FakeDistortion }
})

vi.mock('tone', () => ({
  MembraneSynth: FakeMembraneSynth,
  Synth: FakeSynth,
  NoiseSynth: FakeNoiseSynth,
  MetalSynth: FakeMetalSynth,
  Filter: FakeFilter,
  Distortion: FakeDistortion,
  getContext: () => ({}),
}))

vi.mock('./loader', () => ({
  getDrumBus: () => ({ connect: () => ({}) }),
}))

import { makeSynthKit } from './synthDrums'

// GM drum pitches used across the tests (mirrors the constants in synthDrums.ts)
const KICK = 36
const SNARE = 38
const CLAP = 39
const CLOSED_HAT = 42
const OPEN_HAT = 46
const CRASH = 49
const RIDE = 51
const TOM = 45

function fakeOut() {
  return { connect: () => ({}) } as any
}
function fakeContext() {
  return {} as any
}

describe('makeSynthKit', () => {
  beforeEach(() => {
    createdInstances.length = 0
  })

  it('never retriggers a voice before its envelope window closes, across every drum piece', () => {
    // 'acoustic' carries the longest decays (cymbalDecay 1.8s, rideDecay 0.9s) —
    // the worst case for the timing bug this guards against.
    const kit = makeSynthKit('acoustic', fakeOut(), fakeContext())
    const pitches = [KICK, SNARE, CLAP, CLOSED_HAT, OPEN_HAT, CRASH, RIDE, TOM]
    expect(() => {
      // Hammer every piece with hits close enough together (50ms) that a
      // pool of 4 will eventually wrap around onto an instance that's still
      // "ringing" — exactly the scenario that broke three times over.
      for (let i = 0; i < 20; i++) {
        for (const pitch of pitches) {
          kit.trigger(pitch, 0.8, i * 0.05)
        }
      }
    }).not.toThrow()
  })

  it('round-robins across multiple instances instead of reusing one voice', () => {
    const kit = makeSynthKit('acoustic', fakeOut(), fakeContext())
    for (let i = 0; i < 8; i++) kit.trigger(RIDE, 0.8, i * 2)   // plenty of gap — pooling is the only reason this needs >1 instance
    const rideInstances = createdInstances.filter(v => v instanceof FakeMetalSynth)
    expect(rideInstances.length).toBeGreaterThan(1)
  })

  it('gives MetalSynth-based voices (hats/crash/ride) the note argument they require', () => {
    // Regression test for the argument-arity bug: closedHat/openHat/crash/ride
    // calls used to omit the note argument, silently shifting duration into
    // the note slot, time into the duration slot, and velocity into the time
    // slot. FakeVoice's arity check makes that shape throw immediately.
    const kit = makeSynthKit('acoustic', fakeOut(), fakeContext())
    expect(() => kit.trigger(CLOSED_HAT, 0.8, 1.0)).not.toThrow()
    expect(() => kit.trigger(OPEN_HAT, 0.8, 2.0)).not.toThrow()
    expect(() => kit.trigger(CRASH, 0.8, 3.0)).not.toThrow()
    expect(() => kit.trigger(RIDE, 0.8, 4.0)).not.toThrow()
  })

  it('fires the clap "second slap" on a different instance without colliding', () => {
    const kit = makeSynthKit('acoustic', fakeOut(), fakeContext())
    expect(() => kit.trigger(CLAP, 0.8, 1.0)).not.toThrow()
    const clapInstances = createdInstances.filter(v => v instanceof FakeNoiseSynth)
    const totalClapCalls = clapInstances.reduce((sum, v) => sum + v.calls.length, 0)
    expect(totalClapCalls).toBe(2)   // main hit + second slap
  })

  it('handles an unknown percussion pitch by falling back to the closed hat', () => {
    const kit = makeSynthKit('acoustic', fakeOut(), fakeContext())
    expect(() => kit.trigger(999, 0.8, 1.0)).not.toThrow()
  })
})
