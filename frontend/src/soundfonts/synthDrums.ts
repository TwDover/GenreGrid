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

interface Preset {
  kickNote: string
  kickPitchDecay: number
  kickOctaves: number
  kickDecay: number
  subNote: string           // dedicated sub-sine layer note (the "boom")
  subDecay: number          // how long the sub tail rings
  subLevel: number          // sub layer volume in dB (lower = less boom)
  snareToneFreq: number
  snareToneMix: number      // 0–1 weight of the tonal "crack" vs noise body
  snareNoiseDecay: number
  hatFreq: number
  hatDecay: number          // closed-hat decay; open/crash/ride scale off this
  hatHarmonicity: number
  hatModIndex: number
  cymbalDecay: number       // crash length
  rideDecay: number
  masterLPF: number         // kit-wide low-pass for warmth (20000 = off)
  drive: number             // subtle saturation amount (0 = clean)
}

const PRESETS: Record<DrumCharacter, Preset> = {
  // Warm, rounded, longer decays — jazz / latin / cinematic
  acoustic:  { kickNote: 'C1', kickPitchDecay: 0.06, kickOctaves: 4,  kickDecay: 0.58, subNote: 'C1', subDecay: 0.55, subLevel: -11, snareToneFreq: 190, snareToneMix: 0.5,  snareNoiseDecay: 0.20, hatFreq: 380, hatDecay: 0.05, hatHarmonicity: 5.1, hatModIndex: 24, cymbalDecay: 1.8, rideDecay: 0.9, masterLPF: 15000, drive: 0.0 },
  // Tight, forward, classic drum-machine snap — soul / rnb / funk (LINN)
  punchy:    { kickNote: 'C1', kickPitchDecay: 0.04, kickOctaves: 5,  kickDecay: 0.46, subNote: 'C1', subDecay: 0.48, subLevel: -9,  snareToneFreq: 210, snareToneMix: 0.55, snareNoiseDecay: 0.16, hatFreq: 430, hatDecay: 0.04, hatHarmonicity: 5.4, hatModIndex: 30, cymbalDecay: 1.4, rideDecay: 0.7, masterLPF: 17000, drive: 0.08 },
  // Dusty, filtered, soft transients — lofi / cloud rap / ambient
  lofi:      { kickNote: 'B0', kickPitchDecay: 0.07, kickOctaves: 4,  kickDecay: 0.52, subNote: 'B0', subDecay: 0.6,  subLevel: -7,  snareToneFreq: 170, snareToneMix: 0.4,  snareNoiseDecay: 0.14, hatFreq: 320, hatDecay: 0.035,hatHarmonicity: 4.2, hatModIndex: 18, cymbalDecay: 1.1, rideDecay: 0.6, masterLPF: 8500,  drive: 0.05 },
  // Thin, retro, quirky — the CR-78 feel
  vintage:   { kickNote: 'C1', kickPitchDecay: 0.05, kickOctaves: 5,  kickDecay: 0.34, subNote: 'C1', subDecay: 0.35, subLevel: -15, snareToneFreq: 220, snareToneMix: 0.35, snareNoiseDecay: 0.12, hatFreq: 500, hatDecay: 0.03, hatHarmonicity: 6.0, hatModIndex: 22, cymbalDecay: 1.0, rideDecay: 0.5, masterLPF: 12000, drive: 0.0 },
  // Clean, bright digital PCM — R-8, dancehall / reggaeton
  digital:   { kickNote: 'B0', kickPitchDecay: 0.045,kickOctaves: 5,  kickDecay: 0.50, subNote: 'A0', subDecay: 0.55, subLevel: -6,  snareToneFreq: 200, snareToneMix: 0.5,  snareNoiseDecay: 0.18, hatFreq: 460, hatDecay: 0.045,hatHarmonicity: 5.6, hatModIndex: 32, cymbalDecay: 1.5, rideDecay: 0.8, masterLPF: 18000, drive: 0.0 },
  // Hard, tight, sub-heavy — house / techno / dnb
  techno:    { kickNote: 'A0', kickPitchDecay: 0.035,kickOctaves: 6,  kickDecay: 0.44, subNote: 'A0', subDecay: 0.6,  subLevel: -4,  snareToneFreq: 180, snareToneMix: 0.4,  snareNoiseDecay: 0.15, hatFreq: 520, hatDecay: 0.04, hatHarmonicity: 5.8, hatModIndex: 34, cymbalDecay: 1.3, rideDecay: 0.7, masterLPF: 19000, drive: 0.12 },
  // Sampled hip-hop breakbeat feel — boom bap / trap
  breakbeat: { kickNote: 'A0', kickPitchDecay: 0.05, kickOctaves: 5,  kickDecay: 0.5,  subNote: 'A0', subDecay: 0.62, subLevel: -5,  snareToneFreq: 200, snareToneMix: 0.5,  snareNoiseDecay: 0.19, hatFreq: 400, hatDecay: 0.05, hatHarmonicity: 4.8, hatModIndex: 26, cymbalDecay: 1.5, rideDecay: 0.8, masterLPF: 13000, drive: 0.1 },
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
const POOL_SIZE = 4

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
 * Build a synthesized drum kit. `out` defaults to the drum submix bus; the offline
 * renderer passes its own compressor so the kit lives in the offline audio graph.
 * `context` should be passed explicitly by the offline renderer too — otherwise every
 * node here falls back to Tone's ambient context, which is the live-playback context.
 */
export function makeSynthKit(
  character: DrumCharacter = 'acoustic',
  out: Tone.ToneAudioNode = getDrumBus(),
  context: Tone.BaseContext = Tone.getContext(),
): SynthKit {
  const p = PRESETS[character] ?? PRESETS.acoustic
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
    oscillator: { type: 'sine' },
    envelope: { attack: 0.001, decay: p.kickDecay, sustain: 0, release: 0.04 },
    volume: -1,
  })).connect(kitOut))
  // Dedicated sub-sine — this is the "boom". Runs under the membrane at the
  // fundamental with a slow rounded decay; per-preset level controls how deep.
  const nextKickSub = makePool(() => keep(new Tone.Synth({
    context,
    oscillator: { type: 'sine' },
    envelope: { attack: 0.004, decay: p.subDecay, sustain: 0, release: 0.08 },
    volume: p.subLevel,
  })).connect(kitOut))
  // Beater click for attack definition (kept low so the low end dominates)
  const kickClickFilter = keep(new Tone.Filter({ context, frequency: 1600, type: 'highpass' })).connect(kitOut)
  const nextKickClick = makePool(() => keep(new Tone.NoiseSynth({
    context,
    noise: { type: 'white' },
    envelope: { attack: 0.001, decay: 0.02, sustain: 0, release: 0.03 },
    volume: -22,
  })).connect(kickClickFilter))

  // ── Snare: tonal crack + noise body ───────────────────────────────────────
  const snareNoiseBP = keep(new Tone.Filter({ context, frequency: 1800, type: 'bandpass', Q: 0.7 })).connect(kitOut)
  const nextSnareNoise = makePool(() => keep(new Tone.NoiseSynth({
    context,
    noise: { type: 'white' },
    envelope: { attack: 0.001, decay: p.snareNoiseDecay, sustain: 0, release: 0.03 },
    volume: -8,
  })).connect(snareNoiseBP))
  const nextSnareTone = makePool(() => keep(new Tone.Synth({
    context,
    oscillator: { type: 'triangle' },
    envelope: { attack: 0.001, decay: 0.12, sustain: 0, release: 0.02 },
    volume: -12 + Math.round(p.snareToneMix * 8),
  })).connect(kitOut))

  // ── Clap: two fast noise bursts ───────────────────────────────────────────
  const clapBP = keep(new Tone.Filter({ context, frequency: 1200, type: 'bandpass', Q: 1.2 })).connect(kitOut)
  const nextClap = makePool(() => keep(new Tone.NoiseSynth({
    context,
    noise: { type: 'pink' },
    envelope: { attack: 0.001, decay: 0.14, sustain: 0, release: 0.04 },
    volume: -9,
  })).connect(clapBP))

  // ── Hats & cymbals: MetalSynth voices with real decay ─────────────────────
  const hatHP = keep(new Tone.Filter({ context, frequency: 7000, type: 'highpass' })).connect(kitOut)
  const nextClosedHat = makePool(() => {
    const h = keep(new Tone.MetalSynth({
      context,
      envelope: { attack: 0.001, decay: p.hatDecay, sustain: 0, release: 0.01 },
      harmonicity: p.hatHarmonicity, modulationIndex: p.hatModIndex, resonance: 4000, octaves: 1.5,
      volume: -16,
    }))
    h.frequency.value = p.hatFreq
    h.connect(hatHP)
    return h
  })

  const nextOpenHat = makePool(() => {
    const h = keep(new Tone.MetalSynth({
      context,
      envelope: { attack: 0.001, decay: p.hatDecay * 7, sustain: 0.02, release: 0.2 },
      harmonicity: p.hatHarmonicity * 0.7, modulationIndex: p.hatModIndex * 0.6, resonance: 3500, octaves: 1.8,
      volume: -18,
    }))
    h.frequency.value = p.hatFreq * 0.85
    h.connect(hatHP)
    return h
  })

  const cymbalHP = keep(new Tone.Filter({ context, frequency: 4000, type: 'highpass' })).connect(kitOut)
  const nextCrash = makePool(() => {
    const c = keep(new Tone.MetalSynth({
      context,
      envelope: { attack: 0.001, decay: p.cymbalDecay, sustain: 0, release: 0.6 },
      harmonicity: 4.5, modulationIndex: 40, resonance: 5000, octaves: 2.2,
      volume: -22,
    }))
    c.frequency.value = 300
    c.connect(cymbalHP)
    return c
  })

  const nextRide = makePool(() => {
    const r = keep(new Tone.MetalSynth({
      context,
      envelope: { attack: 0.001, decay: p.rideDecay, sustain: 0.04, release: 0.3 },
      harmonicity: 3.4, modulationIndex: 16, resonance: 6000, octaves: 1.6,
      volume: -20,
    }))
    r.frequency.value = 520
    r.connect(cymbalHP)
    return r
  })

  // ── Toms: one pitched membrane voice ──────────────────────────────────────
  const nextTom = makePool(() => keep(new Tone.MembraneSynth({
    context,
    pitchDecay: 0.08, octaves: 3,
    oscillator: { type: 'sine' },
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
  const SNARE_TONE_GAP = 0.001 + 0.12
  const CLAP_GAP = 0.001 + 0.14
  const CLOSED_HAT_GAP = 0.001 + p.hatDecay
  const OPEN_HAT_GAP = 0.001 + p.hatDecay * 7
  const CRASH_GAP = 0.001 + p.cymbalDecay
  const RIDE_GAP = 0.001 + p.rideDecay
  const TOM_GAP = 0.001 + 0.4

  const trigger = (pitch: number, velocity: number, time: number): void => {
    const v = clamp(velocity)
    if (KICK.has(pitch)) {
      const kick = nextKick(); kick.triggerAttackRelease(p.kickNote, p.kickDecay, scheduleVoice(kick, time, KICK_GAP), v)
      const kickSub = nextKickSub(); kickSub.triggerAttackRelease(p.subNote, p.subDecay, scheduleVoice(kickSub, time, KICK_SUB_GAP), v)
      const kickClick = nextKickClick(); kickClick.triggerAttackRelease(0.02, scheduleVoice(kickClick, time, KICK_CLICK_GAP), v)
    } else if (SNARE.has(pitch)) {
      const snareNoise = nextSnareNoise(); snareNoise.triggerAttackRelease(p.snareNoiseDecay, scheduleVoice(snareNoise, time, SNARE_NOISE_GAP), v)
      const snareTone = nextSnareTone(); snareTone.triggerAttackRelease(p.snareToneFreq, 0.1, scheduleVoice(snareTone, time, SNARE_TONE_GAP), v * p.snareToneMix)
    } else if (pitch === CLAP) {
      const clap1 = nextClap(); clap1.triggerAttackRelease(0.14, scheduleVoice(clap1, time, CLAP_GAP), v)
      const clap2 = nextClap(); clap2.triggerAttackRelease(0.1, scheduleVoice(clap2, time + 0.012, CLAP_GAP), v * 0.7)   // second slap
    } else if (CLOSED_HAT.has(pitch)) {
      // MetalSynth has no dedicated triggerAttackRelease override, so it takes the
      // generic Instrument signature (note, duration, time, velocity) — the note arg
      // must be passed explicitly or every argument after it shifts by one slot.
      const hat = nextClosedHat(); hat.triggerAttackRelease(p.hatFreq, p.hatDecay, scheduleVoice(hat, time, CLOSED_HAT_GAP), v * 0.9)
    } else if (pitch === OPEN_HAT) {
      const hat = nextOpenHat(); hat.triggerAttackRelease(p.hatFreq * 0.85, p.hatDecay * 7, scheduleVoice(hat, time, OPEN_HAT_GAP), v * 0.85)
    } else if (CRASH.has(pitch)) {
      const c = nextCrash(); c.triggerAttackRelease(300, p.cymbalDecay, scheduleVoice(c, time, CRASH_GAP), v * 0.8)
    } else if (RIDE.has(pitch)) {
      const r = nextRide(); r.triggerAttackRelease(520, p.rideDecay, scheduleVoice(r, time, RIDE_GAP), v * 0.85)
    } else if (TOM_NOTE[pitch]) {
      const tom = nextTom(); tom.triggerAttackRelease(TOM_NOTE[pitch], 0.35, scheduleVoice(tom, time, TOM_GAP), v)
    } else {
      const hat = nextClosedHat(); hat.triggerAttackRelease(p.hatFreq, p.hatDecay, scheduleVoice(hat, time, CLOSED_HAT_GAP), v * 0.7)   // unknown perc → tick
    }
  }

  return { trigger, nodes }
}
