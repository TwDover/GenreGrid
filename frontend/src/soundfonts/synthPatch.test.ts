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
  patchToNodeSpec,
  PRESET_MELODY_LEAD_SOFT,
  PRESET_SYNTH_LEAD,
  PRESET_SYNTH_CHORDS,
  PRESET_ARP_PLUCK,
  PRESET_PAD,
  PRESET_STRINGS,
  PRESET_SYNTH_BASS,
  PRESET_LOFI,
  type SynthNodeSpec,
} from './synthPatch'

// ── Parity gate ───────────────────────────────────────────────────────────────
// jsdom has no Web Audio, so we can't render audio to compare samples. Instead we
// pin the pure node-graph description (`patchToNodeSpec`) each preset produces to a
// transcription of that voice's PRE-migration factory config in synthVoices.ts.
// Identical constructor options + chain order ⇒ identical Tone graph ⇒ identical
// audio by construction, so these snapshots ARE the "untouched songs stay
// byte-identical" guarantee: change a preset (or the spec logic) and this breaks.
//
// Each expected value below is copied straight from the factory it replaces —
// values the factory omitted (Tone defaults) are written explicitly (Q:1,
// rolloff:-12), which is exactly what the migrated code now passes.
describe('patchToNodeSpec — byte-identical parity with the old synthVoices factories', () => {
  const cases: Array<[string, Parameters<typeof patchToNodeSpec>[0], SynthNodeSpec]> = [
    ['makeMelodyLead(soft)', PRESET_MELODY_LEAD_SOFT, {
      voice: 'poly',
      synthOptions: {
        oscillator: { type: 'triangle' },
        envelope: { attack: 0.03, decay: 0.2, sustain: 0.75, release: 0.8 },
        volume: -9,
      },
      chain: [{ node: 'Filter', options: { type: 'lowpass', frequency: 3000, Q: 0.8, rolloff: -12 } }],
    }],
    ['makeMelodyLead(hard)', PRESET_SYNTH_LEAD, {
      voice: 'poly',
      synthOptions: {
        oscillator: { type: 'sawtooth' },
        envelope: { attack: 0.008, decay: 0.15, sustain: 0.65, release: 0.3 },
        volume: -10,
      },
      chain: [{ node: 'Filter', options: { type: 'lowpass', frequency: 3800, Q: 0.8, rolloff: -12 } }],
    }],
    ['makeSynthChords', PRESET_SYNTH_CHORDS, {
      voice: 'poly',
      synthOptions: {
        oscillator: { type: 'fatsawtooth', count: 3, spread: 22 },
        envelope: { attack: 0.06, decay: 0.25, sustain: 0.65, release: 0.6 },
        volume: -15,
      },
      chain: [{ node: 'Filter', options: { type: 'lowpass', frequency: 2600, Q: 1, rolloff: -12 } }],
    }],
    ['makeArpPluck', PRESET_ARP_PLUCK, {
      voice: 'poly',
      synthOptions: {
        oscillator: { type: 'triangle' },
        envelope: { attack: 0.004, decay: 0.18, sustain: 0.0, release: 0.25 },
        volume: -12,
      },
      chain: [{ node: 'Filter', options: { type: 'lowpass', frequency: 4200, Q: 1, rolloff: -12 } }],
    }],
    ['makePad', PRESET_PAD, {
      voice: 'poly',
      synthOptions: {
        oscillator: { type: 'triangle' },
        envelope: { attack: 0.8, decay: 0.3, sustain: 0.7, release: 2.0 },
        volume: -10,
      },
      chain: [],
    }],
    ['makeStrings', PRESET_STRINGS, {
      voice: 'poly',
      synthOptions: {
        oscillator: { type: 'fatsawtooth', count: 3, spread: 14 },
        envelope: { attack: 0.12, decay: 0.3, sustain: 0.8, release: 1.2 },
        volume: -14,
      },
      chain: [{ node: 'Filter', options: { type: 'lowpass', frequency: 2400, Q: 1, rolloff: -12 } }],
    }],
    ['makeSynthBass', PRESET_SYNTH_BASS, {
      voice: 'mono',
      synthOptions: {
        oscillator: { type: 'sawtooth' },
        envelope: { attack: 0.01, decay: 0.08, sustain: 0.9, release: 0.3 },
        volume: -3,
        filter: { type: 'lowpass', Q: 2.5, rolloff: -24 },
        filterEnvelope: { attack: 0.04, decay: 0.2, sustain: 0.5, release: 0.3, baseFrequency: 180, octaves: 2.6 },
        portamento: 0.035,
      },
      chain: [],
    }],
    ['makeLofiSynth', PRESET_LOFI, {
      voice: 'poly',
      synthOptions: {
        oscillator: { type: 'triangle' },
        envelope: { attack: 0.04, decay: 0.2, sustain: 0.6, release: 1.2 },
        volume: -4,
      },
      chain: [
        { node: 'BitCrusher', options: { bits: 10 } },
        { node: 'Filter', options: { type: 'lowpass', frequency: 5500, Q: 1, rolloff: -12 } },
        { node: 'Vibrato', options: { frequency: 2.5, depth: 0.04, wet: 1 } },
      ],
    }],
  ]

  for (const [name, patch, expected] of cases) {
    it(`${name} renders the same node graph as before the migration`, () => {
      expect(patchToNodeSpec(patch)).toEqual(expected)
    })
  }
})

// ── Shape / ordering invariants ───────────────────────────────────────────────
describe('patchToNodeSpec — chain shape', () => {
  it('orders the chain synth → bitcrusher → filter → vibrato → output', () => {
    // Lo-fi is the only built-in exercising all three FX nodes.
    expect(patchToNodeSpec(PRESET_LOFI).chain.map(n => n.node)).toEqual(['BitCrusher', 'Filter', 'Vibrato'])
  })

  it('keeps the mono voice filter + filter envelope inside the synth, with an empty chain', () => {
    const spec = patchToNodeSpec(PRESET_SYNTH_BASS)
    expect(spec.voice).toBe('mono')
    expect(spec.chain).toEqual([])
    expect(spec.synthOptions.filter).toBeDefined()
    expect(spec.synthOptions.filterEnvelope).toBeDefined()
  })

  it('gives a filterless poly voice (pad) an empty chain', () => {
    expect(patchToNodeSpec(PRESET_PAD).chain).toEqual([])
  })

  it('omits unison count/spread for a plain (non-fat) oscillator', () => {
    expect(patchToNodeSpec(PRESET_PAD).synthOptions.oscillator).toEqual({ type: 'triangle' })
  })

  it('carries unison count/spread for a fat oscillator', () => {
    expect(patchToNodeSpec(PRESET_SYNTH_CHORDS).synthOptions.oscillator).toEqual({ type: 'fatsawtooth', count: 3, spread: 22 })
  })
})
