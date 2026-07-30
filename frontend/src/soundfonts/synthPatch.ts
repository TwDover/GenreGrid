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

// ── Subtractive synth patch: pure data + a factory that renders it ────────────
//
// Roadmap 6.6 turns a part's timbre from a hand-coded Tone factory into a piece of
// serializable DATA (`SynthPatch`) rendered by a single pure factory
// (`buildSynthFromPatch`) — the same "pure core, no bespoke function per voice"
// discipline as voiceRouting.ts / layeredSampler.ts. This first slice defines the
// shape, the factory, and expresses the seven built-in voices (synthVoices.ts) as
// preset patches so the shape is proven expressive enough. It is ADDITIVE: no part
// is assigned a patch yet, so every existing song still renders byte-identically —
// the migration is gated by `patchToNodeSpec` (a pure node-graph description) whose
// output is asserted to equal each old factory's config in synthPatch.test.ts.
//
// `patchToNodeSpec` is the framework-free seam: it turns a patch into the exact
// constructor options + chain order that `buildSynthFromPatch` will instantiate, so
// the audio graph can be regression-tested in jsdom (which has no Web Audio) without
// ever creating a Tone node.
import * as Tone from 'tone'
import { getMelodicBus } from './loader'

// The oscillator waves the built-ins use, plus Tone's `fat*` unison variants. Pulse
// / sub-osc / wavetable are reserved for later designer slices — added here only as
// the shape grows, never speculatively.
export type OscillatorWave =
  | 'sine' | 'triangle' | 'sawtooth' | 'square' | 'pulse'
  | 'fatsine' | 'fattriangle' | 'fatsawtooth' | 'fatsquare'

export interface OscillatorSpec {
  type: OscillatorWave
  /** Unison voice count — only meaningful for `fat*` waves. */
  count?: number
  /** Unison detune spread in cents — only meaningful for `fat*` waves. */
  spread?: number
}

export interface ADSR {
  attack: number
  decay: number
  sustain: number
  release: number
}

/** Amp envelope + the synth's output level in dB (Tone's `volume`). */
export interface AmpEnvelopeSpec extends ADSR {
  level: number
}

export type FilterType = 'lowpass' | 'highpass' | 'bandpass'
export type FilterRolloff = -12 | -24 | -48 | -96

export interface FilterSpec {
  type: FilterType
  /** Omitted for the mono voice, whose cutoff is driven by the filter envelope's
   *  `baseFrequency` (matching Tone's `MonoSynth` filter). */
  frequency?: number
  Q: number
  rolloff: FilterRolloff
}

/** The moving filter of a `MonoSynth` (its ADSR plus base cutoff and sweep depth). */
export interface FilterEnvelopeSpec extends ADSR {
  baseFrequency: number
  octaves: number
}

export interface BitcrusherFx {
  bits: number
}

export interface VibratoFx {
  frequency: number
  depth: number
  wet: number
}

/** Inline FX the built-ins use (lo-fi). Chorus/delay live on the shared melodic bus
 *  today, so they are intentionally NOT in the patch yet (added in the FX slice). */
export interface FxChain {
  bitcrusher?: BitcrusherFx
  vibrato?: VibratoFx
}

/**
 * A subtractive synth voice as pure, serializable data — the third instrument source
 * alongside *sampled* and *custom*. `engine` is a discriminator from day one so FM /
 * wavetable land later as new variants instead of a schema break (roadmap 6.6).
 */
export interface SynthPatch {
  engine: 'subtractive'
  /** `poly` → PolySynth(Synth) with an optional external filter; `mono` → MonoSynth
   *  whose filter + filter envelope are built in (the bass voice). */
  voice: 'poly' | 'mono'
  oscillator: OscillatorSpec
  ampEnvelope: AmpEnvelopeSpec
  filter?: FilterSpec
  filterEnvelope?: FilterEnvelopeSpec
  /** Glide time in seconds (mono bass). */
  portamento?: number
  fx?: FxChain
}

// ── Pure node-graph description (the testable seam) ───────────────────────────

export type ChainNodeKind = 'BitCrusher' | 'Filter' | 'Vibrato'

export interface ChainNodeSpec {
  node: ChainNodeKind
  options: Record<string, number | string>
}

export interface SynthNodeSpec {
  voice: 'poly' | 'mono'
  /** Constructor options for PolySynth(Synth) or MonoSynth. */
  synthOptions: Record<string, unknown>
  /** FX/filter nodes between the synth and the output, in synth→output order. */
  chain: ChainNodeSpec[]
}

function oscillatorOptions(o: OscillatorSpec): Record<string, number | string> {
  const opts: Record<string, number | string> = { type: o.type }
  if (o.count !== undefined) opts.count = o.count
  if (o.spread !== undefined) opts.spread = o.spread
  return opts
}

function envelopeOptions(e: ADSR): Record<string, number> {
  return { attack: e.attack, decay: e.decay, sustain: e.sustain, release: e.release }
}

/**
 * Derive the exact constructor options + chain order a patch renders to — no Tone
 * nodes, no AudioContext, so it runs in jsdom and is the target of the parity gate.
 *
 * Canonical signal chain (verified against all seven built-ins):
 *   synth → [bitcrusher] → [filter] → [vibrato] → output
 * For the `mono` voice the filter + filter envelope are constructor options of the
 * MonoSynth itself (not a chain node), matching Tone.
 */
export function patchToNodeSpec(patch: SynthPatch): SynthNodeSpec {
  const synthOptions: Record<string, unknown> = {
    oscillator: oscillatorOptions(patch.oscillator),
    envelope: envelopeOptions(patch.ampEnvelope),
    volume: patch.ampEnvelope.level,
  }

  if (patch.voice === 'mono') {
    if (patch.filter) {
      const f: Record<string, number | string> = { type: patch.filter.type, Q: patch.filter.Q, rolloff: patch.filter.rolloff }
      if (patch.filter.frequency !== undefined) f.frequency = patch.filter.frequency
      synthOptions.filter = f
    }
    if (patch.filterEnvelope) {
      synthOptions.filterEnvelope = {
        ...envelopeOptions(patch.filterEnvelope),
        baseFrequency: patch.filterEnvelope.baseFrequency,
        octaves: patch.filterEnvelope.octaves,
      }
    }
    if (patch.portamento !== undefined) synthOptions.portamento = patch.portamento
    // Mono's filter is internal; no external chain nodes today.
    return { voice: 'mono', synthOptions, chain: [] }
  }

  const chain: ChainNodeSpec[] = []
  if (patch.fx?.bitcrusher) chain.push({ node: 'BitCrusher', options: { bits: patch.fx.bitcrusher.bits } })
  if (patch.filter) {
    const f: Record<string, number | string> = {
      type: patch.filter.type,
      frequency: patch.filter.frequency ?? 0,
      Q: patch.filter.Q,
      rolloff: patch.filter.rolloff,
    }
    chain.push({ node: 'Filter', options: f })
  }
  if (patch.fx?.vibrato) {
    chain.push({ node: 'Vibrato', options: { frequency: patch.fx.vibrato.frequency, depth: patch.fx.vibrato.depth, wet: patch.fx.vibrato.wet } })
  }
  return { voice: 'poly', synthOptions, chain }
}

// ── The factory: build real Tone nodes from a patch ───────────────────────────

type ToneVoice = Tone.PolySynth | Tone.MonoSynth

function makeChainNode(spec: ChainNodeSpec): Tone.ToneAudioNode {
  switch (spec.node) {
    case 'BitCrusher':
      return new Tone.BitCrusher(spec.options as ConstructorParameters<typeof Tone.BitCrusher>[0])
    case 'Filter':
      return new Tone.Filter(spec.options as ConstructorParameters<typeof Tone.Filter>[0])
    case 'Vibrato':
      return new Tone.Vibrato(spec.options as ConstructorParameters<typeof Tone.Vibrato>[0])
  }
}

/**
 * Assemble a Tone voice + its FX chain from a patch and connect it to `output`,
 * registering every created node in `disposables` (the existing synthVoices.ts
 * pattern, now generated from data). Returns the voice the scheduler triggers.
 *
 * Nodes are built output-first so `disposables` mirrors the old factories' push
 * order (output-adjacent → synth). The resulting graph + params are exactly what
 * `patchToNodeSpec` describes, so a patch rebuilt anywhere renders identically.
 */
export function buildSynthFromPatch(
  patch: SynthPatch,
  disposables: Tone.ToneAudioNode[],
  output: Tone.ToneAudioNode = getMelodicBus(),
): ToneVoice {
  const spec = patchToNodeSpec(patch)

  // Chain: instantiate from the output end back toward the synth.
  let downstream: Tone.ToneAudioNode = output
  for (let i = spec.chain.length - 1; i >= 0; i--) {
    const node = makeChainNode(spec.chain[i])
    node.connect(downstream)
    disposables.push(node)
    downstream = node
  }

  const voice: ToneVoice = spec.voice === 'mono'
    ? new Tone.MonoSynth(spec.synthOptions as ConstructorParameters<typeof Tone.MonoSynth>[0])
    : new Tone.PolySynth(Tone.Synth, spec.synthOptions as ConstructorParameters<typeof Tone.Synth>[0])
  voice.connect(downstream)
  disposables.push(voice)
  return voice
}

// ── The seven built-in voices as preset patches ───────────────────────────────
//
// Each field is the corresponding synthVoices.ts factory's EFFECTIVE value — set
// explicitly even where the factory relied on a Tone default (e.g. Filter Q/rolloff),
// so passing it reproduces that default and the render stays byte-identical.

/** makeMelodyLead(soft=true): warm triangle lead behind a gentle low-pass. */
export const PRESET_MELODY_LEAD_SOFT: SynthPatch = {
  engine: 'subtractive',
  voice: 'poly',
  oscillator: { type: 'triangle' },
  ampEnvelope: { attack: 0.03, decay: 0.2, sustain: 0.75, release: 0.8, level: -9 },
  filter: { type: 'lowpass', frequency: 3000, Q: 0.8, rolloff: -12 },
}

/** makeMelodyLead(soft=false): articulate sawtooth lead. */
export const PRESET_SYNTH_LEAD: SynthPatch = {
  engine: 'subtractive',
  voice: 'poly',
  oscillator: { type: 'sawtooth' },
  ampEnvelope: { attack: 0.008, decay: 0.15, sustain: 0.65, release: 0.3, level: -10 },
  filter: { type: 'lowpass', frequency: 3800, Q: 0.8, rolloff: -12 },
}

/** makeSynthChords: detuned/warm saw stack, darker than the lead. */
export const PRESET_SYNTH_CHORDS: SynthPatch = {
  engine: 'subtractive',
  voice: 'poly',
  oscillator: { type: 'fatsawtooth', count: 3, spread: 22 },
  ampEnvelope: { attack: 0.06, decay: 0.25, sustain: 0.65, release: 0.6, level: -15 },
  filter: { type: 'lowpass', frequency: 2600, Q: 1, rolloff: -12 },
}

/** makeArpPluck: short bright decaying pluck (sustain 0). */
export const PRESET_ARP_PLUCK: SynthPatch = {
  engine: 'subtractive',
  voice: 'poly',
  oscillator: { type: 'triangle' },
  ampEnvelope: { attack: 0.004, decay: 0.18, sustain: 0.0, release: 0.25, level: -12 },
  filter: { type: 'lowpass', frequency: 4200, Q: 1, rolloff: -12 },
}

/** makePad: slow-attack triangle wash, no filter (straight to the bus). */
export const PRESET_PAD: SynthPatch = {
  engine: 'subtractive',
  voice: 'poly',
  oscillator: { type: 'triangle' },
  ampEnvelope: { attack: 0.8, decay: 0.3, sustain: 0.7, release: 2.0, level: -10 },
}

/** makeStrings: soft detuned-saw ensemble for the counter-melody. */
export const PRESET_STRINGS: SynthPatch = {
  engine: 'subtractive',
  voice: 'poly',
  oscillator: { type: 'fatsawtooth', count: 3, spread: 14 },
  ampEnvelope: { attack: 0.12, decay: 0.3, sustain: 0.8, release: 1.2, level: -14 },
  filter: { type: 'lowpass', frequency: 2400, Q: 1, rolloff: -12 },
}

/** makeSynthBass: sawtooth MonoSynth with a moving filter + portamento. */
export const PRESET_SYNTH_BASS: SynthPatch = {
  engine: 'subtractive',
  voice: 'mono',
  oscillator: { type: 'sawtooth' },
  ampEnvelope: { attack: 0.01, decay: 0.08, sustain: 0.9, release: 0.3, level: -3 },
  filter: { type: 'lowpass', Q: 2.5, rolloff: -24 },
  filterEnvelope: { attack: 0.04, decay: 0.2, sustain: 0.5, release: 0.3, baseFrequency: 180, octaves: 2.6 },
  portamento: 0.035,
}

/** makeLofiSynth: warm triangle → bitcrusher → low-pass → vibrato. */
export const PRESET_LOFI: SynthPatch = {
  engine: 'subtractive',
  voice: 'poly',
  oscillator: { type: 'triangle' },
  ampEnvelope: { attack: 0.04, decay: 0.2, sustain: 0.6, release: 1.2, level: -4 },
  filter: { type: 'lowpass', frequency: 5500, Q: 1, rolloff: -12 },
  fx: { bitcrusher: { bits: 10 }, vibrato: { frequency: 2.5, depth: 0.04, wet: 1 } },
}
