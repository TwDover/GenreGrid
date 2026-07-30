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

/** A per-note pitch drop (mono voices): the note starts `semitones` above pitch and
 *  falls to it over `decay` seconds — the classic 808/kick attack transient. */
export interface PitchEnvelopeSpec {
  semitones: number
  decay: number
}

export interface BitcrusherFx {
  bits: number
}

export interface VibratoFx {
  frequency: number
  depth: number
  wet: number
}

/** Overdrive/distortion. `amount` is Tone's `distortion` 0..1. */
export interface DriveFx {
  amount: number
  wet: number
}

export interface ChorusFx {
  frequency: number
  depth: number
  wet: number
}

export interface DelayFx {
  /** Delay time in seconds (used when `sync` is false). */
  time: number
  sync: boolean
  /** Tempo-synced delay time as a note value, e.g. '8n', '8n.'. */
  syncTime: string
  feedback: number
  wet: number
}

export interface ReverbFx {
  /** Tail length in seconds (Tone's `decay`). */
  decay: number
  wet: number
}

/** The per-voice FX chain. Every field is optional and absent on all built-ins except
 *  lo-fi (bitcrusher + vibrato), so adding an effect never touches an existing render.
 *  Order here is cosmetic; patchToNodeSpec fixes the signal-chain order. */
export interface FxChain {
  drive?: DriveFx
  bitcrusher?: BitcrusherFx
  chorus?: ChorusFx
  vibrato?: VibratoFx
  delay?: DelayFx
  reverb?: ReverbFx
}

export type LfoWave = 'sine' | 'triangle' | 'sawtooth' | 'square'
/** Where a single LFO is routed: `filter` sweeps the external filter cutoff (poly
 *  voices with a filter); `amp` is tremolo — a modulated gain at the output. Pitch
 *  vibrato is the existing `fx.vibrato`, so it's not an LFO destination here. */
export type LfoDestination = 'filter' | 'amp'

export interface LfoSpec {
  destination: LfoDestination
  wave: LfoWave
  /** Free-running rate in Hz (used when `sync` is false). */
  rateHz: number
  /** When true, the LFO runs at `syncRate` (a note value) instead of `rateHz`. */
  sync: boolean
  /** Tempo-synced rate as a note value, e.g. '8n', '4n.', '8t'. */
  syncRate: string
  /** 0..1 modulation amount. */
  depth: number
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
  /** A per-note pitch drop — mono voices only (drives the MonoSynth's detune). */
  pitchEnvelope?: PitchEnvelopeSpec
  /** Glide time in seconds (mono bass). */
  portamento?: number
  fx?: FxChain
  /** A single LFO (poly voices). Absent on every built-in, so it never changes an
   *  existing render. */
  lfo?: LfoSpec
}

// ── Pure node-graph description (the testable seam) ───────────────────────────

export type ChainNodeKind =
  | 'BitCrusher' | 'Filter' | 'Vibrato' | 'Gain'
  | 'Distortion' | 'Chorus' | 'FeedbackDelay' | 'Reverb'

export interface ChainNodeSpec {
  node: ChainNodeKind
  options: Record<string, number | string>
}

/** A modulation routing: one LFO driving a target audio param. The target is a role,
 *  not a node index, because there is at most one of each modulatable node. */
export interface ModSpec {
  lfo: { frequency: number | string; type: LfoWave; min: number; max: number }
  target: 'filterFrequency' | 'ampGain'
}

export interface SynthNodeSpec {
  voice: 'poly' | 'mono'
  /** Constructor options for PolySynth(Synth) or MonoSynth. */
  synthOptions: Record<string, unknown>
  /** FX/filter nodes between the synth and the output, in synth→output order. */
  chain: ChainNodeSpec[]
  /** Present only when the patch has an LFO that resolves to a valid target. */
  mod?: ModSpec
  /** Present only for a mono voice with a pitch envelope (drives its detune). */
  pitchEnv?: PitchEnvelopeSpec
}

// Cutoff bounds shared by the filter-LFO range maths (and the designer's log slider).
const CUTOFF_MIN_HZ = 20
const CUTOFF_MAX_HZ = 12000
/** Octaves the filter LFO opens above the base cutoff at full depth. */
const LFO_FILTER_OCTAVES = 4

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
    // Mono's filter is internal (part of the MonoSynth), so it isn't a chain node —
    // but the FX chain still applies (a driven/saturated 808 needs its distortion).
    // LFO stays poly-only (its filter target needs an external Filter node).
    const spec: SynthNodeSpec = { voice: 'mono', synthOptions, chain: buildFxChain(patch.fx, null) }
    if (patch.pitchEnvelope) spec.pitchEnv = { semitones: patch.pitchEnvelope.semitones, decay: patch.pitchEnvelope.decay }
    return spec
  }

  // Poly voice: same FX chain, but the filter is an EXTERNAL node in the middle of it.
  const filterNode: ChainNodeSpec | null = patch.filter
    ? { node: 'Filter', options: { type: patch.filter.type, frequency: patch.filter.frequency ?? 0, Q: patch.filter.Q, rolloff: patch.filter.rolloff } }
    : null
  const chain = buildFxChain(patch.fx, filterNode)
  const mod = lfoMod(patch.lfo, chain)
  return mod ? { voice: 'poly', synthOptions, chain, mod } : { voice: 'poly', synthOptions, chain }
}

// Canonical signal order (synth → output). `filterNode` is the external filter for a
// poly voice (a mono voice's filter is internal, so it passes null). New effects slot
// in around the bitcrusher/filter/vibrato so the lo-fi voice's chain is byte-identical.
//   drive → bitcrusher → [filter] → chorus → vibrato → delay → reverb → [tremolo gain]
function buildFxChain(fx: FxChain | undefined, filterNode: ChainNodeSpec | null): ChainNodeSpec[] {
  const chain: ChainNodeSpec[] = []
  if (fx?.drive) chain.push({ node: 'Distortion', options: { distortion: fx.drive.amount, wet: fx.drive.wet } })
  if (fx?.bitcrusher) chain.push({ node: 'BitCrusher', options: { bits: fx.bitcrusher.bits } })
  if (filterNode) chain.push(filterNode)
  if (fx?.chorus) chain.push({ node: 'Chorus', options: { frequency: fx.chorus.frequency, depth: fx.chorus.depth, wet: fx.chorus.wet } })
  if (fx?.vibrato) chain.push({ node: 'Vibrato', options: { frequency: fx.vibrato.frequency, depth: fx.vibrato.depth, wet: fx.vibrato.wet } })
  if (fx?.delay) chain.push({ node: 'FeedbackDelay', options: { delayTime: fx.delay.sync ? fx.delay.syncTime : fx.delay.time, feedback: fx.delay.feedback, wet: fx.delay.wet } })
  if (fx?.reverb) chain.push({ node: 'Reverb', options: { decay: fx.reverb.decay, wet: fx.reverb.wet } })
  return chain
}

/**
 * Resolve an LFO into a modulation spec, appending the tremolo Gain node to `chain`
 * when the destination is `amp`. Returns undefined when there's no LFO or its target
 * doesn't exist (e.g. a filter LFO on a filterless patch), so an unroutable LFO is a
 * no-op rather than an error.
 */
function lfoMod(lfo: LfoSpec | undefined, chain: ChainNodeSpec[]): ModSpec | undefined {
  if (!lfo) return undefined
  const frequency = lfo.sync ? lfo.syncRate : lfo.rateHz

  if (lfo.destination === 'amp') {
    // Tremolo: a modulated gain at the output end, swinging between (1−depth) and 1.
    chain.push({ node: 'Gain', options: { gain: 1 } })
    return { lfo: { frequency, type: lfo.wave, min: 1 - lfo.depth, max: 1 }, target: 'ampGain' }
  }

  // Filter cutoff: sweep upward from the base cutoff by up to LFO_FILTER_OCTAVES.
  const filterNode = chain.find(n => n.node === 'Filter')
  if (!filterNode) return undefined
  const base = Number(filterNode.options.frequency) || 1000
  const min = Math.max(CUTOFF_MIN_HZ, Math.round(base))
  const max = Math.min(CUTOFF_MAX_HZ, Math.round(base * 2 ** (lfo.depth * LFO_FILTER_OCTAVES)))
  return { lfo: { frequency, type: lfo.wave, min, max }, target: 'filterFrequency' }
}

// ── The factory: build real Tone nodes from a patch ───────────────────────────

type ToneVoice = Tone.PolySynth | Tone.MonoSynth

// When `context` is given (offline export), it must be threaded into every node's
// options so the node is created on the OfflineAudioContext, not the global one.
function nodeOpts(spec: ChainNodeSpec, context?: Tone.BaseContext): Record<string, unknown> {
  return context ? { ...spec.options, context } : spec.options
}

function makeChainNode(spec: ChainNodeSpec, context?: Tone.BaseContext): Tone.ToneAudioNode {
  const opts = nodeOpts(spec, context)
  switch (spec.node) {
    case 'BitCrusher':
      return new Tone.BitCrusher(opts as ConstructorParameters<typeof Tone.BitCrusher>[0])
    case 'Filter':
      return new Tone.Filter(opts as ConstructorParameters<typeof Tone.Filter>[0])
    case 'Vibrato':
      return new Tone.Vibrato(opts as ConstructorParameters<typeof Tone.Vibrato>[0])
    case 'Gain':
      return new Tone.Gain(opts as ConstructorParameters<typeof Tone.Gain>[0])
    case 'Distortion':
      return new Tone.Distortion(opts as ConstructorParameters<typeof Tone.Distortion>[0])
    case 'Chorus':
      // Chorus's internal LFO doesn't auto-run (unlike Vibrato), so start it — matching
      // the offline render's chorus.start().
      return new Tone.Chorus(opts as ConstructorParameters<typeof Tone.Chorus>[0]).start()
    case 'FeedbackDelay':
      return new Tone.FeedbackDelay(opts as ConstructorParameters<typeof Tone.FeedbackDelay>[0])
    case 'Reverb':
      return new Tone.Reverb(opts as ConstructorParameters<typeof Tone.Reverb>[0])
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
 *
 * `context` is for **offline export**: pass the OfflineAudioContext so every node is
 * created on it. Omit it for live playback (nodes use the global context, exactly as
 * before — byte-identical). Same patch + same graph either way; only the host context
 * (and the `output` you pass) differ, which is what makes a patch render the same in
 * playback and export.
 */
export function buildSynthFromPatch(
  patch: SynthPatch,
  disposables: Tone.ToneAudioNode[],
  output: Tone.ToneAudioNode = getMelodicBus(),
  context?: Tone.BaseContext,
): ToneVoice {
  const spec = patchToNodeSpec(patch)

  // Chain: instantiate from the output end back toward the synth, keeping each node
  // by its chain index so a modulation target can be found afterwards.
  const built: Tone.ToneAudioNode[] = []
  let downstream: Tone.ToneAudioNode = output
  for (let i = spec.chain.length - 1; i >= 0; i--) {
    const node = makeChainNode(spec.chain[i], context)
    node.connect(downstream)
    disposables.push(node)
    built[i] = node
    downstream = node
  }

  const voice: ToneVoice = spec.voice === 'mono'
    ? new Tone.MonoSynth((context ? { context, ...spec.synthOptions } : spec.synthOptions) as ConstructorParameters<typeof Tone.MonoSynth>[0])
    : context
      ? new Tone.PolySynth({ context, voice: Tone.Synth, options: spec.synthOptions } as ConstructorParameters<typeof Tone.PolySynth>[0])
      : new Tone.PolySynth(Tone.Synth, spec.synthOptions as ConstructorParameters<typeof Tone.Synth>[0])
  voice.connect(downstream)
  disposables.push(voice)

  if (spec.mod) wireMod(spec, built, disposables, context)
  if (spec.pitchEnv) attachPitchEnv(voice, spec.pitchEnv, disposables, context)
  return voice
}

/**
 * Attach a per-note pitch drop to a mono voice: a `Tone.Envelope` scaled to the depth
 * in cents, summed into the synth's `detune`. Tone's Mono/PolySynth have no pitch
 * envelope, and only the monophonic voices expose a `detune` signal — so this wraps
 * the voice's `triggerAttackRelease` (the sole trigger entry point every call site
 * uses) to fire the envelope alongside each note. Envelope 1→0 over `decay` makes the
 * pitch start `semitones` high and fall to the note.
 */
function attachPitchEnv(voice: ToneVoice, pe: PitchEnvelopeSpec, disposables: Tone.ToneAudioNode[], context?: Tone.BaseContext): void {
  const detune = (voice as Tone.MonoSynth).detune as Tone.Signal<'cents'> | undefined
  if (!detune) return   // poly voices have no single detune; pitch env is mono-only
  const ctx = context ? { context } : {}
  const env = new Tone.Envelope({ ...ctx, attack: 0.001, decay: pe.decay, sustain: 0, release: 0.001 })
  const depth = new Tone.Gain({ ...ctx, gain: pe.semitones * 100 })   // env (0..1) → cents
  env.connect(depth)
  depth.connect(detune)
  disposables.push(env, depth)

  const orig = voice.triggerAttackRelease.bind(voice)
  ;(voice as unknown as { triggerAttackRelease: (n: string, d: number, t: number, v: number) => void }).triggerAttackRelease =
    (note: string, duration: number, time: number, velocity: number) => {
      env.triggerAttackRelease(duration, time)
      orig(note, duration, time, velocity)
    }
}

/** Build the LFO and connect it to its target param (the tremolo Gain's gain, or the
 *  filter's frequency). A missing target node is skipped, matching patchToNodeSpec's
 *  "unroutable LFO is a no-op" contract. */
function wireMod(spec: SynthNodeSpec, built: Tone.ToneAudioNode[], disposables: Tone.ToneAudioNode[], context?: Tone.BaseContext): void {
  const mod = spec.mod!
  const targetKind: ChainNodeKind = mod.target === 'ampGain' ? 'Gain' : 'Filter'
  const node = built.find((_, i) => spec.chain[i].node === targetKind)
  if (!node) return
  const param = mod.target === 'ampGain'
    ? (node as Tone.Gain).gain
    : (node as Tone.Filter).frequency
  const lfo = new Tone.LFO((context ? { ...mod.lfo, context } : mod.lfo) as ConstructorParameters<typeof Tone.LFO>[0])
  lfo.connect(param)
  lfo.start()
  disposables.push(lfo)
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

// ── Bass character patches (808 family) ───────────────────────────────────────
// An 808 is a mono voice: a pure low oscillator, an amp envelope that BOOMS out on
// note-off (long release), and portamento so notes SLIDE into each other — the
// signature 808 glide. The trap variant adds drive so the sub grows harmonics and
// reads on phones/laptops, not just subs.

/** 808 Sub — clean, round West-Coast/G-funk sub. Sine fundamental, gentle glide,
 *  boomy release; the low-pass keeps it pure. */
export const PRESET_808_SUB: SynthPatch = {
  engine: 'subtractive',
  voice: 'mono',
  oscillator: { type: 'sine' },
  ampEnvelope: { attack: 0.006, decay: 0.3, sustain: 0.7, release: 1.1, level: -2 },
  filter: { type: 'lowpass', Q: 1, rolloff: -24 },
  filterEnvelope: { attack: 0.006, decay: 0.4, sustain: 0.5, release: 0.9, baseFrequency: 110, octaves: 1.6 },
  pitchEnvelope: { semitones: 4, decay: 0.05 },
  portamento: 0.06,
}

/** 808 Trap — booming, saturated 808 for trap/drill. Triangle for harmonics to bite
 *  into, pronounced glide, long ringing release, and drive for the distorted growl. */
export const PRESET_808_TRAP: SynthPatch = {
  engine: 'subtractive',
  voice: 'mono',
  oscillator: { type: 'triangle' },
  ampEnvelope: { attack: 0.004, decay: 0.5, sustain: 0.75, release: 1.6, level: -3 },
  filter: { type: 'lowpass', Q: 1.2, rolloff: -24 },
  filterEnvelope: { attack: 0.004, decay: 0.35, sustain: 0.55, release: 0.7, baseFrequency: 90, octaves: 2.2 },
  pitchEnvelope: { semitones: 8, decay: 0.06 },
  portamento: 0.08,
  fx: { drive: { amount: 0.35, wet: 0.55 } },
}

/** 808 Boom — the pure one: a clean SINE sub with a full-octave pitch drop for the
 *  "dooom" punch and a long decaying boom tail. No drive, so it stays deep and round
 *  rather than growly. The classic sampled-808 shape, synthesized. Best heard at
 *  C1–C2 (drop the designer keyboard's octave). */
export const PRESET_808_BOOM: SynthPatch = {
  engine: 'subtractive',
  voice: 'mono',
  oscillator: { type: 'sine' },
  ampEnvelope: { attack: 0.003, decay: 0.9, sustain: 0.55, release: 1.8, level: -2 },
  filter: { type: 'lowpass', Q: 1, rolloff: -24 },
  filterEnvelope: { attack: 0.005, decay: 0.3, sustain: 0.6, release: 0.5, baseFrequency: 140, octaves: 1.2 },
  pitchEnvelope: { semitones: 12, decay: 0.09 },
  portamento: 0.05,
}

// ── Curated library: strong starting patches per role ─────────────────────────

/** Reese Bass — DnB/neuro: a detuned saw stack, dark and moving, with a slow amp-LFO
 *  on the cutoff for the growling wobble and light drive for grit. */
export const PRESET_REESE_BASS: SynthPatch = {
  engine: 'subtractive',
  voice: 'poly',
  oscillator: { type: 'fatsawtooth', count: 3, spread: 32 },
  ampEnvelope: { attack: 0.008, decay: 0.2, sustain: 0.9, release: 0.4, level: -10 },
  filter: { type: 'lowpass', frequency: 520, Q: 3, rolloff: -24 },
  lfo: { destination: 'filter', wave: 'triangle', rateHz: 1.2, sync: false, syncRate: '8n', depth: 0.5 },
  fx: { drive: { amount: 0.25, wet: 0.4 } },
}

/** Supersaw Lead — trance/EDM: seven detuned saws, bright and wide, with chorus, a
 *  synced delay, and a touch of reverb for the anthemic top line. */
export const PRESET_SUPERSAW_LEAD: SynthPatch = {
  engine: 'subtractive',
  voice: 'poly',
  oscillator: { type: 'fatsawtooth', count: 7, spread: 40 },
  ampEnvelope: { attack: 0.02, decay: 0.2, sustain: 0.8, release: 0.5, level: -16 },
  filter: { type: 'lowpass', frequency: 6000, Q: 0.7, rolloff: -12 },
  fx: {
    chorus: { frequency: 0.8, depth: 0.4, wet: 0.3 },
    delay: { time: 0.25, sync: true, syncTime: '8n', feedback: 0.28, wet: 0.2 },
    reverb: { decay: 2.5, wet: 0.2 },
  },
}

/** Warm Pad — analog-style wash: fat detuned saws, slow attack, gentle low-pass, with
 *  chorus and a long reverb for the bed. */
export const PRESET_WARM_PAD: SynthPatch = {
  engine: 'subtractive',
  voice: 'poly',
  oscillator: { type: 'fatsawtooth', count: 3, spread: 25 },
  ampEnvelope: { attack: 0.6, decay: 0.4, sustain: 0.85, release: 2.4, level: -14 },
  filter: { type: 'lowpass', frequency: 1800, Q: 0.8, rolloff: -12 },
  fx: { chorus: { frequency: 0.5, depth: 0.5, wet: 0.35 }, reverb: { decay: 4, wet: 0.35 } },
}

/** Pluck — short, bright synth pluck with a synced delay tail for arps/stabs. */
export const PRESET_PLUCK: SynthPatch = {
  engine: 'subtractive',
  voice: 'poly',
  oscillator: { type: 'sawtooth' },
  ampEnvelope: { attack: 0.002, decay: 0.16, sustain: 0.0, release: 0.2, level: -12 },
  filter: { type: 'lowpass', frequency: 3200, Q: 1.5, rolloff: -12 },
  fx: { delay: { time: 0.25, sync: true, syncTime: '8n.', feedback: 0.3, wet: 0.22 }, reverb: { decay: 1.4, wet: 0.18 } },
}

/** Acid Bass — TB-303 style: a saw through a high-resonance low-pass with a strong
 *  filter-envelope sweep, glide, and drive for the squelch. */
export const PRESET_ACID_BASS: SynthPatch = {
  engine: 'subtractive',
  voice: 'mono',
  oscillator: { type: 'sawtooth' },
  ampEnvelope: { attack: 0.005, decay: 0.2, sustain: 0.5, release: 0.2, level: -6 },
  filter: { type: 'lowpass', Q: 8, rolloff: -24 },
  filterEnvelope: { attack: 0.005, decay: 0.22, sustain: 0.2, release: 0.2, baseFrequency: 220, octaves: 3.5 },
  portamento: 0.05,
  fx: { drive: { amount: 0.4, wet: 0.5 } },
}

// ── Built-in patch registry ───────────────────────────────────────────────────
// Every built-in patch addressable by a stable slug, so the designer's preset menu,
// per-part assignment resolution, and style kits all reference one source of truth.
// A slug can be stored as an assignment value (resolved by useSynthPatches) exactly
// like a saved-library id.
export interface BuiltinPatchEntry { label: string; patch: SynthPatch }

export const BUILTIN_PATCHES: Record<string, BuiltinPatchEntry> = {
  melody_lead_soft: { label: 'Melody Lead (soft)', patch: PRESET_MELODY_LEAD_SOFT },
  synth_lead: { label: 'Synth Lead', patch: PRESET_SYNTH_LEAD },
  synth_chords: { label: 'Synth Chords', patch: PRESET_SYNTH_CHORDS },
  arp_pluck: { label: 'Arp Pluck', patch: PRESET_ARP_PLUCK },
  pad: { label: 'Pad', patch: PRESET_PAD },
  strings: { label: 'Strings', patch: PRESET_STRINGS },
  synth_bass: { label: 'Synth Bass', patch: PRESET_SYNTH_BASS },
  '808_sub': { label: '808 Sub (bass)', patch: PRESET_808_SUB },
  '808_boom': { label: '808 Boom (bass)', patch: PRESET_808_BOOM },
  '808_trap': { label: '808 Trap (bass)', patch: PRESET_808_TRAP },
  reese_bass: { label: 'Reese Bass', patch: PRESET_REESE_BASS },
  acid_bass: { label: 'Acid Bass', patch: PRESET_ACID_BASS },
  supersaw_lead: { label: 'Supersaw Lead', patch: PRESET_SUPERSAW_LEAD },
  warm_pad: { label: 'Warm Pad', patch: PRESET_WARM_PAD },
  pluck: { label: 'Pluck', patch: PRESET_PLUCK },
  lofi: { label: 'Lo-fi', patch: PRESET_LOFI },
}

/** A built-in patch by slug, or undefined. */
export function builtinPatch(slug: string): SynthPatch | undefined {
  return BUILTIN_PATCHES[slug]?.patch
}
