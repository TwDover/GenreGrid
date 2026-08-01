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
import * as Tone from 'tone'
import { getDrumBus } from './loader'

/**
 * Synthesized drum engine.
 *
 * Replaces the old sample path, which relied on 5 KB vintage one-shots and — worse —
 * fabricated crash/ride/open-hat as byte-identical copies of the closed hi-hat, so
 * every cymbal was a click. Here each articulation is its own synth voice with a
 * real envelope: kicks have a pitch drop and body, snares blend tone + noise, and
 * cymbals actually ring and decay. Voices are separate instruments so they never
 * choke each other (only a voice retriggering itself cuts off, which is realistic).
 *
 * Character presets tune the voices toward each kit's genre feel.
 */

export type DrumCharacter =
  | 'acoustic' | 'punchy' | 'lofi' | 'vintage' | 'digital' | 'techno' | 'breakbeat'

/** The tonal-voice oscillator waves usable per drum piece. A subset of
 *  `OscillatorWave` in synthPatch.ts — drum bodies are single membrane/tone
 *  voices, so unison (`fat*`) waves don't apply here. */
export type DrumOscWave = 'sine' | 'triangle' | 'sawtooth' | 'square'
/** Noise color for the drum designer's noise-driven layers (click/snare/clap). */
export type DrumNoiseType = 'white' | 'pink' | 'brown'

/**
 * A synthesized drum kit as pure, serializable data — the drum-side analog of
 * `SynthPatch`. Every numeric knob a kit character used to hardcode is here, plus
 * the oscillator/noise choices each voice used to bake in inline, so a user can
 * design a kick, snare, or hat from its raw tones (roadmap: drum voice designer).
 */
export interface DrumKitPatch {
  kickNote: string
  kickOscType: DrumOscWave
  kickPitchDecay: number
  kickOctaves: number
  kickDecay: number
  subNote: string           // dedicated sub-sine layer note (the "boom")
  subOscType: DrumOscWave
  subDecay: number          // how long the sub tail rings
  subLevel: number          // sub layer volume in dB (lower = less boom)
  clickNoiseType: DrumNoiseType
  snareToneFreq: number
  snareToneOscType: DrumOscWave
  snareToneMix: number      // 0–1 weight of the tonal "crack" vs noise body
  snareNoiseType: DrumNoiseType
  snareNoiseDecay: number
  /** 0–1 weight of a second, brighter "wire buzz" noise layer blended under the
   *  main snare noise — real snares are a skin transient PLUS a separate, longer,
   *  higher-pitched buzz from the snare wires; this is that second layer. */
  snareBuzzMix: number
  clapNoiseType: DrumNoiseType
  hatFreq: number
  hatDecay: number          // closed-hat decay; open/crash/ride scale off this
  hatHarmonicity: number
  hatModIndex: number
  cymbalDecay: number       // crash length
  rideDecay: number
  tomOscType: DrumOscWave
  masterLPF: number         // kit-wide low-pass for warmth (20000 = off)
  drive: number             // subtle saturation amount (0 = clean)
  /** 0–1 amount of per-hit micro-variation (pitch/level jitter on kick, snare tone
   *  and toms; stereo pan jitter on hats/cymbals) — real kits never hit identically
   *  twice; this is what keeps a kit from reading as sequenced/robotic. 0 = off. */
  humanize: number
  /** An uploaded drum sample kit (a `CustomInstrument` id, `kind: 'drums'`, from the
   *  Instruments panel library) to blend under this synth kit — a real sample as a
   *  base to design around, not just a full sample-kit override. Undefined = pure
   *  synth (see `makeBlendedKit` in customDrumKit.ts). */
  sampleKitId?: string
  /** 0–1 kit-wide mix between the synth (0) and the sample (1) for any piece the
   *  sample kit covers; pieces it doesn't cover stay pure synth regardless. */
  sampleBlend: number
}

export interface BuiltinKitEntry { label: string; patch: DrumKitPatch }

export const BUILTIN_KITS: Record<DrumCharacter, BuiltinKitEntry> = {
  // Warm, rounded, longer decays — jazz / latin / cinematic
  acoustic: { label: 'Acoustic', patch: { kickNote: 'C1', kickOscType: 'sine', kickPitchDecay: 0.06, kickOctaves: 4,  kickDecay: 0.58, subNote: 'C1', subOscType: 'sine', subDecay: 0.55, subLevel: -11, clickNoiseType: 'white', snareToneFreq: 190, snareToneOscType: 'triangle', snareToneMix: 0.5,  snareNoiseType: 'white', snareNoiseDecay: 0.20, snareBuzzMix: 0.35, clapNoiseType: 'pink', hatFreq: 380, hatDecay: 0.05, hatHarmonicity: 5.1, hatModIndex: 24, cymbalDecay: 1.8, rideDecay: 0.9, tomOscType: 'sine', masterLPF: 15000, drive: 0.0, humanize: 0.30, sampleBlend: 0 } },
  // Tight, forward, classic drum-machine snap — soul / rnb / funk (LINN)
  punchy: { label: 'Punchy', patch: { kickNote: 'C1', kickOscType: 'sine', kickPitchDecay: 0.04, kickOctaves: 5,  kickDecay: 0.46, subNote: 'C1', subOscType: 'sine', subDecay: 0.48, subLevel: -9,  clickNoiseType: 'white', snareToneFreq: 210, snareToneOscType: 'triangle', snareToneMix: 0.55, snareNoiseType: 'white', snareNoiseDecay: 0.16, snareBuzzMix: 0.45, clapNoiseType: 'pink', hatFreq: 430, hatDecay: 0.04, hatHarmonicity: 5.4, hatModIndex: 30, cymbalDecay: 1.4, rideDecay: 0.7, tomOscType: 'sine', masterLPF: 17000, drive: 0.08, humanize: 0.15, sampleBlend: 0 } },
  // Dusty, filtered, soft transients — lofi / cloud rap / ambient
  lofi: { label: 'Lo-fi', patch: { kickNote: 'B0', kickOscType: 'sine', kickPitchDecay: 0.07, kickOctaves: 4,  kickDecay: 0.52, subNote: 'B0', subOscType: 'sine', subDecay: 0.6,  subLevel: -7,  clickNoiseType: 'white', snareToneFreq: 170, snareToneOscType: 'triangle', snareToneMix: 0.4,  snareNoiseType: 'white', snareNoiseDecay: 0.14, snareBuzzMix: 0.25, clapNoiseType: 'pink', hatFreq: 320, hatDecay: 0.035,hatHarmonicity: 4.2, hatModIndex: 18, cymbalDecay: 1.1, rideDecay: 0.6, tomOscType: 'sine', masterLPF: 8500,  drive: 0.05, humanize: 0.35, sampleBlend: 0 } },
  // Thin, retro, quirky — the CR-78 feel
  vintage: { label: 'Vintage', patch: { kickNote: 'C1', kickOscType: 'sine', kickPitchDecay: 0.05, kickOctaves: 5,  kickDecay: 0.34, subNote: 'C1', subOscType: 'sine', subDecay: 0.35, subLevel: -15, clickNoiseType: 'white', snareToneFreq: 220, snareToneOscType: 'triangle', snareToneMix: 0.35, snareNoiseType: 'white', snareNoiseDecay: 0.12, snareBuzzMix: 0.30, clapNoiseType: 'pink', hatFreq: 500, hatDecay: 0.03, hatHarmonicity: 6.0, hatModIndex: 22, cymbalDecay: 1.0, rideDecay: 0.5, tomOscType: 'sine', masterLPF: 12000, drive: 0.0, humanize: 0.25, sampleBlend: 0 } },
  // Clean, bright digital PCM — R-8, dancehall / reggaeton
  digital: { label: 'Digital', patch: { kickNote: 'B0', kickOscType: 'sine', kickPitchDecay: 0.045,kickOctaves: 5,  kickDecay: 0.50, subNote: 'A0', subOscType: 'sine', subDecay: 0.55, subLevel: -6,  clickNoiseType: 'white', snareToneFreq: 200, snareToneOscType: 'triangle', snareToneMix: 0.5,  snareNoiseType: 'white', snareNoiseDecay: 0.18, snareBuzzMix: 0.50, clapNoiseType: 'pink', hatFreq: 460, hatDecay: 0.045,hatHarmonicity: 5.6, hatModIndex: 32, cymbalDecay: 1.5, rideDecay: 0.8, tomOscType: 'sine', masterLPF: 18000, drive: 0.0, humanize: 0.05, sampleBlend: 0 } },
  // Hard, tight, sub-heavy — house / techno / dnb
  techno: { label: 'Techno', patch: { kickNote: 'A0', kickOscType: 'sine', kickPitchDecay: 0.035,kickOctaves: 6,  kickDecay: 0.44, subNote: 'A0', subOscType: 'sine', subDecay: 0.6,  subLevel: -4,  clickNoiseType: 'white', snareToneFreq: 180, snareToneOscType: 'triangle', snareToneMix: 0.4,  snareNoiseType: 'white', snareNoiseDecay: 0.15, snareBuzzMix: 0.40, clapNoiseType: 'pink', hatFreq: 520, hatDecay: 0.04, hatHarmonicity: 5.8, hatModIndex: 34, cymbalDecay: 1.3, rideDecay: 0.7, tomOscType: 'sine', masterLPF: 19000, drive: 0.12, humanize: 0.08, sampleBlend: 0 } },
  // Sampled hip-hop breakbeat feel — boom bap / trap
  breakbeat: { label: 'Breakbeat', patch: { kickNote: 'A0', kickOscType: 'sine', kickPitchDecay: 0.05, kickOctaves: 5,  kickDecay: 0.5,  subNote: 'A0', subOscType: 'sine', subDecay: 0.62, subLevel: -5,  clickNoiseType: 'white', snareToneFreq: 200, snareToneOscType: 'triangle', snareToneMix: 0.5,  snareNoiseType: 'white', snareNoiseDecay: 0.19, snareBuzzMix: 0.40, clapNoiseType: 'pink', hatFreq: 400, hatDecay: 0.05, hatHarmonicity: 4.8, hatModIndex: 26, cymbalDecay: 1.5, rideDecay: 0.8, tomOscType: 'sine', masterLPF: 13000, drive: 0.1, humanize: 0.28, sampleBlend: 0 } },
}

/** A built-in kit's patch by character slug. */
export function builtinKitPatch(character: DrumCharacter): DrumKitPatch {
  return BUILTIN_KITS[character]?.patch ?? BUILTIN_KITS.acoustic.patch
}

// GM drum pitch → voice
const KICK = new Set([35, 36])
const SNARE = new Set([38, 40])
const CLAP = 39
const CLOSED_HAT = new Set([42, 44])
const OPEN_HAT = 46
const CRASH = new Set([49, 52, 55, 57])
const RIDE = new Set([51, 53, 59])
// Toms: pitch → semitone offset from a base tom frequency
const TOM_NOTE: Record<number, string> = {
  41: 'G1', 43: 'A1', 45: 'C2', 47: 'D2', 48: 'F2', 50: 'G2',
}

export interface SynthKit {
  trigger: (pitch: number, velocity: number, time: number) => void
  nodes: Tone.ToneAudioNode[]
}

// Every synth voice below schedules an internal auto-stop on its own oscillator/noise
// source once its envelope's sustain is 0 (which all of ours are — MetalSynth forces
// this internally regardless of what's passed in). Retriggering the *same* source
// again before that internal bookkeeping catches up can violate Tone's requirement
// that a source's successive start times never go backwards, throwing "the time must
// be greater than or equal to the last scheduled time". Rather than reproducing Tone's
// internal stop-scheduling math to compute a safe minimum gap (fragile, and does not
// hold up under dense/fast patterns), each drum piece round-robins across a small pool
// of instances so no single underlying source is ever retriggered as often as the
// pattern itself calls trigger() for that piece.
//
// Kept small (2, not 4): the four MetalSynth voices (closed/open hat, crash, ride) are
// heavy FM synths, and POOL_SIZE * 4 of them overwhelmed the audio render thread on Linux
// packaged Electron — it rendered one buffer then the whole output stream died (silent).
// 8 total is safely under that limit; scheduleVoice() below still guarantees retrigger
// safety when a piece is hit faster than its pool can recover.
const POOL_SIZE = 2

function makePool<T extends Tone.ToneAudioNode>(factory: () => T): () => T {
  const instances = Array.from({ length: POOL_SIZE }, factory)
  let i = 0
  return () => {
    const instance = instances[i]
    i = (i + 1) % POOL_SIZE
    return instance
  }
}

/**
 * Build a synthesized drum kit from a patch. `out` defaults to the drum submix bus;
 * the offline renderer passes its own compressor so the kit lives in the offline
 * audio graph. `context` should be passed explicitly by the offline renderer too —
 * otherwise every node here falls back to Tone's ambient context, which is the
 * live-playback context.
 */
export function makeSynthKit(
  patch: DrumKitPatch = BUILTIN_KITS.acoustic.patch,
  out: Tone.ToneAudioNode = getDrumBus(),
  context: Tone.BaseContext = Tone.getContext(),
): SynthKit {
  const p = patch
  const nodes: Tone.ToneAudioNode[] = []
  const keep = <T extends Tone.ToneAudioNode>(n: T): T => { nodes.push(n); return n }

  // Kit-wide tone shaping: optional warmth LPF + gentle saturation into the bus.
  const master = keep(new Tone.Filter({ context, frequency: p.masterLPF, type: 'lowpass', rolloff: -12 })).connect(out)
  const kitOut: Tone.ToneAudioNode = p.drive > 0
    ? (() => { const d = keep(new Tone.Distortion({ context, distortion: p.drive, wet: 0.35 })); d.connect(master); return d })()
    : master

  // ── Kick: pitch-swept body + sub layer + beater click ─────────────────────
  const nextKick = makePool(() => keep(new Tone.MembraneSynth({
    context,
    pitchDecay: p.kickPitchDecay,
    octaves: p.kickOctaves,
    oscillator: { type: p.kickOscType },
    envelope: { attack: 0.001, decay: p.kickDecay, sustain: 0, release: 0.04 },
    volume: -1,
  })).connect(kitOut))
  // Dedicated sub-sine — this is the "boom". Runs under the membrane at the
  // fundamental with a slow rounded decay; per-preset level controls how deep.
  const nextKickSub = makePool(() => keep(new Tone.Synth({
    context,
    oscillator: { type: p.subOscType },
    envelope: { attack: 0.004, decay: p.subDecay, sustain: 0, release: 0.08 },
    volume: p.subLevel,
  })).connect(kitOut))
  // Beater click for attack definition (kept low so the low end dominates)
  const kickClickFilter = keep(new Tone.Filter({ context, frequency: 1600, type: 'highpass' })).connect(kitOut)
  const nextKickClick = makePool(() => keep(new Tone.NoiseSynth({
    context,
    noise: { type: p.clickNoiseType },
    envelope: { attack: 0.001, decay: 0.02, sustain: 0, release: 0.03 },
    volume: -22,
  })).connect(kickClickFilter))

  // ── Snare: tonal crack + noise body ───────────────────────────────────────
  const snareNoiseBP = keep(new Tone.Filter({ context, frequency: 1800, type: 'bandpass', Q: 0.7 })).connect(kitOut)
  const nextSnareNoise = makePool(() => keep(new Tone.NoiseSynth({
    context,
    noise: { type: p.snareNoiseType },
    envelope: { attack: 0.001, decay: p.snareNoiseDecay, sustain: 0, release: 0.03 },
    volume: -8,
  })).connect(snareNoiseBP))
  const nextSnareTone = makePool(() => keep(new Tone.Synth({
    context,
    oscillator: { type: p.snareToneOscType },
    envelope: { attack: 0.001, decay: 0.12, sustain: 0, release: 0.02 },
    volume: -12 + Math.round(p.snareToneMix * 8),
  })).connect(kitOut))
  // Wire buzz: a second, brighter/thinner noise layer that rings a bit longer than the
  // skin transient above — real snares are the skin hit PLUS a separate buzz off the
  // snare wires, not one noise burst. Decay/level derive from the existing skin knobs
  // (snareNoiseDecay/snareBuzzMix) rather than adding more sliders, same as how
  // open-hat/crash/ride already scale off the closed-hat/crash settings.
  const snareBuzzHP = keep(new Tone.Filter({ context, frequency: 4500, type: 'highpass' })).connect(kitOut)
  const nextSnareBuzz = makePool(() => keep(new Tone.NoiseSynth({
    context,
    noise: { type: p.snareNoiseType },
    envelope: { attack: 0.001, decay: p.snareNoiseDecay * 1.6, sustain: 0, release: 0.05 },
    volume: -18 + Math.round(p.snareBuzzMix * 10),
  })).connect(snareBuzzHP))

  // ── Clap: two fast noise bursts ───────────────────────────────────────────
  const clapBP = keep(new Tone.Filter({ context, frequency: 1200, type: 'bandpass', Q: 1.2 })).connect(kitOut)
  const nextClap = makePool(() => keep(new Tone.NoiseSynth({
    context,
    noise: { type: p.clapNoiseType },
    envelope: { attack: 0.001, decay: 0.14, sustain: 0, release: 0.04 },
    volume: -9,
  })).connect(clapBP))

  // ── Hats & cymbals: MetalSynth voices with real decay ─────────────────────
  // Each pooled instance gets its own Panner so humanize can jitter stereo position
  // per hit (mic'd hats/overheads never sit dead-center identically twice) — tracked
  // in a WeakMap since makePool's factory only returns the instrument itself.
  const metalPanners = new WeakMap<Tone.MetalSynth, Tone.Panner>()
  const hatHP = keep(new Tone.Filter({ context, frequency: 7000, type: 'highpass' })).connect(kitOut)
  const nextClosedHat = makePool(() => {
    const pan = keep(new Tone.Panner({ context, pan: 0 })).connect(hatHP)
    const h = keep(new Tone.MetalSynth({
      context,
      envelope: { attack: 0.001, decay: p.hatDecay, sustain: 0, release: 0.01 },
      harmonicity: p.hatHarmonicity, modulationIndex: p.hatModIndex, resonance: 4000, octaves: 1.5,
      volume: -16,
    }))
    h.frequency.value = p.hatFreq
    h.connect(pan)
    metalPanners.set(h, pan)
    return h
  })

  const nextOpenHat = makePool(() => {
    const pan = keep(new Tone.Panner({ context, pan: 0 })).connect(hatHP)
    const h = keep(new Tone.MetalSynth({
      context,
      envelope: { attack: 0.001, decay: p.hatDecay * 7, sustain: 0.02, release: 0.2 },
      harmonicity: p.hatHarmonicity * 0.7, modulationIndex: p.hatModIndex * 0.6, resonance: 3500, octaves: 1.8,
      volume: -18,
    }))
    h.frequency.value = p.hatFreq * 0.85
    h.connect(pan)
    metalPanners.set(h, pan)
    return h
  })

  const cymbalHP = keep(new Tone.Filter({ context, frequency: 4000, type: 'highpass' })).connect(kitOut)
  const nextCrash = makePool(() => {
    const pan = keep(new Tone.Panner({ context, pan: 0 })).connect(cymbalHP)
    const c = keep(new Tone.MetalSynth({
      context,
      envelope: { attack: 0.001, decay: p.cymbalDecay, sustain: 0, release: 0.6 },
      harmonicity: 4.5, modulationIndex: 40, resonance: 5000, octaves: 2.2,
      volume: -22,
    }))
    c.frequency.value = 300
    c.connect(pan)
    metalPanners.set(c, pan)
    return c
  })

  const nextRide = makePool(() => {
    const pan = keep(new Tone.Panner({ context, pan: 0 })).connect(cymbalHP)
    const r = keep(new Tone.MetalSynth({
      context,
      envelope: { attack: 0.001, decay: p.rideDecay, sustain: 0.04, release: 0.3 },
      harmonicity: 3.4, modulationIndex: 16, resonance: 6000, octaves: 1.6,
      volume: -20,
    }))
    r.frequency.value = 520
    r.connect(pan)
    metalPanners.set(r, pan)
    return r
  })

  // ── Toms: one pitched membrane voice ──────────────────────────────────────
  const nextTom = makePool(() => keep(new Tone.MembraneSynth({
    context,
    pitchDecay: 0.08, octaves: 3,
    oscillator: { type: p.tomOscType },
    envelope: { attack: 0.001, decay: 0.4, sustain: 0, release: 0.05 },
    volume: -8,
  })).connect(kitOut))

  const clamp = (v: number) => Math.max(0.02, Math.min(1, v))

  // Defensive backstop, mathematically sized rather than a fixed epsilon. Every voice
  // above has a sustain:0 envelope, and Tone's *EnvelopeAttack (Synth/MembraneSynth/
  // NoiseSynth/MetalSynth — see node_modules/tone/build/esm/instrument/*.js) always
  // schedules an internal auto-stop at `time + attack + decay` whenever sustain is 0.
  // A separate stop from triggerRelease's `duration` can land earlier and win instead,
  // but never later — so `attack + decay` is a proven upper bound on how soon a given
  // instance actually goes quiet. Retriggering the same pooled instance before that
  // point is what throws; clamping to at least that gap guarantees it never can,
  // regardless of pattern density. Pooling above keeps this from having to engage for
  // anything but the busiest patterns on long-decay voices (ride/crash).
  const busyUntil = new WeakMap<object, number>()
  const TIME_EPSILON = 1e-4
  const scheduleVoice = (voice: object, time: number, minGap: number): number => {
    const earliestSafe = busyUntil.get(voice) ?? -Infinity
    const t = time >= earliestSafe ? time : earliestSafe + TIME_EPSILON
    busyUntil.set(voice, t + minGap)
    return t
  }

  const KICK_GAP = 0.001 + p.kickDecay
  const KICK_SUB_GAP = 0.004 + p.subDecay
  const KICK_CLICK_GAP = 0.001 + 0.02
  const SNARE_NOISE_GAP = 0.001 + p.snareNoiseDecay
  const SNARE_BUZZ_GAP = 0.001 + p.snareNoiseDecay * 1.6
  const SNARE_TONE_GAP = 0.001 + 0.12
  const CLAP_GAP = 0.001 + 0.14
  const CLOSED_HAT_GAP = 0.001 + p.hatDecay
  const OPEN_HAT_GAP = 0.001 + p.hatDecay * 7
  const CRASH_GAP = 0.001 + p.cymbalDecay
  const RIDE_GAP = 0.001 + p.rideDecay
  const TOM_GAP = 0.001 + 0.4

  // Velocity → timbre: real drums get BRIGHTER as well as louder when hit harder, not
  // just louder — a kit that only scales gain with velocity reads as sequenced/static.
  // Applied to hats' FM brightness and the kick-click/snare-noise transient level.
  const bright = (v: number) => 0.8 + v * 0.5   // 0.8x .. 1.3x

  // Per-hit micro-variation ("humanize" — see DrumKitPatch.humanize): real kits never
  // hit identically twice. A no-op (returns the input/does nothing) when humanize is 0,
  // so a kit with humanize:0 renders exactly as before this feature existed.
  const jitterVelocity = (v: number): number =>
    p.humanize > 0 ? clamp(v * (1 + (Math.random() * 2 - 1) * p.humanize * 0.15)) : v
  const jitterDetune = (voice: { detune: Tone.Signal<'cents'> }): void => {
    if (p.humanize > 0) voice.detune.value = (Math.random() * 2 - 1) * p.humanize * 15
  }
  const jitterPan = (voice: Tone.MetalSynth): void => {
    if (p.humanize <= 0) return
    const pan = metalPanners.get(voice)
    if (pan) pan.pan.value = (Math.random() * 2 - 1) * p.humanize * 0.3
  }

  const trigger = (pitch: number, velocity: number, time: number): void => {
    const v = jitterVelocity(clamp(velocity))
    if (KICK.has(pitch)) {
      const kick = nextKick(); jitterDetune(kick)
      kick.triggerAttackRelease(p.kickNote, p.kickDecay, scheduleVoice(kick, time, KICK_GAP), v)
      const kickSub = nextKickSub(); kickSub.triggerAttackRelease(p.subNote, p.subDecay, scheduleVoice(kickSub, time, KICK_SUB_GAP), v)
      const kickClick = nextKickClick(); kickClick.volume.value = -22 + (bright(v) - 1) * 12
      kickClick.triggerAttackRelease(0.02, scheduleVoice(kickClick, time, KICK_CLICK_GAP), v)
    } else if (SNARE.has(pitch)) {
      const snareNoise = nextSnareNoise(); snareNoise.volume.value = -8 + (bright(v) - 1) * 10
      snareNoise.triggerAttackRelease(p.snareNoiseDecay, scheduleVoice(snareNoise, time, SNARE_NOISE_GAP), v)
      const snareBuzz = nextSnareBuzz(); snareBuzz.triggerAttackRelease(p.snareNoiseDecay * 1.6, scheduleVoice(snareBuzz, time, SNARE_BUZZ_GAP), v * p.snareBuzzMix)
      const snareTone = nextSnareTone(); jitterDetune(snareTone)
      snareTone.triggerAttackRelease(p.snareToneFreq, 0.1, scheduleVoice(snareTone, time, SNARE_TONE_GAP), v * p.snareToneMix)
    } else if (pitch === CLAP) {
      const clap1 = nextClap(); clap1.triggerAttackRelease(0.14, scheduleVoice(clap1, time, CLAP_GAP), v)
      const clap2 = nextClap(); clap2.triggerAttackRelease(0.1, scheduleVoice(clap2, time + 0.012, CLAP_GAP), v * 0.7)   // second slap
    } else if (CLOSED_HAT.has(pitch)) {
      // MetalSynth has no dedicated triggerAttackRelease override, so it takes the
      // generic Instrument signature (note, duration, time, velocity) — the note arg
      // must be passed explicitly or every argument after it shifts by one slot.
      const hat = nextClosedHat()
      hat.harmonicity = p.hatHarmonicity * bright(v); hat.modulationIndex = p.hatModIndex * bright(v)
      jitterPan(hat)
      hat.triggerAttackRelease(p.hatFreq, p.hatDecay, scheduleVoice(hat, time, CLOSED_HAT_GAP), v * 0.9)
    } else if (pitch === OPEN_HAT) {
      const hat = nextOpenHat()
      hat.harmonicity = p.hatHarmonicity * 0.7 * bright(v); hat.modulationIndex = p.hatModIndex * 0.6 * bright(v)
      jitterPan(hat)
      hat.triggerAttackRelease(p.hatFreq * 0.85, p.hatDecay * 7, scheduleVoice(hat, time, OPEN_HAT_GAP), v * 0.85)
    } else if (CRASH.has(pitch)) {
      const c = nextCrash(); jitterPan(c)
      c.triggerAttackRelease(300, p.cymbalDecay, scheduleVoice(c, time, CRASH_GAP), v * 0.8)
    } else if (RIDE.has(pitch)) {
      const r = nextRide(); jitterPan(r)
      r.triggerAttackRelease(520, p.rideDecay, scheduleVoice(r, time, RIDE_GAP), v * 0.85)
    } else if (TOM_NOTE[pitch]) {
      const tom = nextTom(); jitterDetune(tom)
      tom.triggerAttackRelease(TOM_NOTE[pitch], 0.35, scheduleVoice(tom, time, TOM_GAP), v)
    } else {
      const hat = nextClosedHat(); hat.triggerAttackRelease(p.hatFreq, p.hatDecay, scheduleVoice(hat, time, CLOSED_HAT_GAP), v * 0.7)   // unknown perc → tick
    }
  }

  return { trigger, nodes }
}
