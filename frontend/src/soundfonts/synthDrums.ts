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

/**
 * Build a synthesized drum kit. `out` defaults to the drum submix bus; the offline
 * renderer passes its own compressor so the kit lives in the offline audio graph.
 */
export function makeSynthKit(
  character: DrumCharacter = 'acoustic',
  out: Tone.ToneAudioNode = getDrumBus(),
): SynthKit {
  const p = PRESETS[character] ?? PRESETS.acoustic
  const nodes: Tone.ToneAudioNode[] = []
  const keep = <T extends Tone.ToneAudioNode>(n: T): T => { nodes.push(n); return n }

  // Kit-wide tone shaping: optional warmth LPF + gentle saturation into the bus.
  const master = keep(new Tone.Filter({ frequency: p.masterLPF, type: 'lowpass', rolloff: -12 })).connect(out)
  const kitOut: Tone.ToneAudioNode = p.drive > 0
    ? (() => { const d = keep(new Tone.Distortion({ distortion: p.drive, wet: 0.35 })); d.connect(master); return d })()
    : master

  // ── Kick: pitch-swept body + sub layer + beater click ─────────────────────
  const kick = keep(new Tone.MembraneSynth({
    pitchDecay: p.kickPitchDecay,
    octaves: p.kickOctaves,
    oscillator: { type: 'sine' },
    envelope: { attack: 0.001, decay: p.kickDecay, sustain: 0, release: 0.04 },
    volume: -1,
  })).connect(kitOut)
  // Dedicated sub-sine — this is the "boom". Runs under the membrane at the
  // fundamental with a slow rounded decay; per-preset level controls how deep.
  const kickSub = keep(new Tone.Synth({
    oscillator: { type: 'sine' },
    envelope: { attack: 0.004, decay: p.subDecay, sustain: 0, release: 0.08 },
    volume: p.subLevel,
  })).connect(kitOut)
  // Beater click for attack definition (kept low so the low end dominates)
  const kickClickFilter = keep(new Tone.Filter({ frequency: 1600, type: 'highpass' })).connect(kitOut)
  const kickClick = keep(new Tone.NoiseSynth({
    noise: { type: 'white' },
    envelope: { attack: 0.001, decay: 0.02, sustain: 0 },
    volume: -22,
  })).connect(kickClickFilter)

  // ── Snare: tonal crack + noise body ───────────────────────────────────────
  const snareNoiseBP = keep(new Tone.Filter({ frequency: 1800, type: 'bandpass', Q: 0.7 })).connect(kitOut)
  const snareNoise = keep(new Tone.NoiseSynth({
    noise: { type: 'white' },
    envelope: { attack: 0.001, decay: p.snareNoiseDecay, sustain: 0, release: 0.03 },
    volume: -8,
  })).connect(snareNoiseBP)
  const snareTone = keep(new Tone.Synth({
    oscillator: { type: 'triangle' },
    envelope: { attack: 0.001, decay: 0.12, sustain: 0, release: 0.02 },
    volume: -12 + Math.round(p.snareToneMix * 8),
  })).connect(kitOut)

  // ── Clap: two fast noise bursts ───────────────────────────────────────────
  const clapBP = keep(new Tone.Filter({ frequency: 1200, type: 'bandpass', Q: 1.2 })).connect(kitOut)
  const clap = keep(new Tone.NoiseSynth({
    noise: { type: 'pink' },
    envelope: { attack: 0.001, decay: 0.14, sustain: 0 },
    volume: -9,
  })).connect(clapBP)

  // ── Hats & cymbals: MetalSynth voices with real decay ─────────────────────
  const hatHP = keep(new Tone.Filter({ frequency: 7000, type: 'highpass' })).connect(kitOut)
  const closedHat = keep(new Tone.MetalSynth({
    envelope: { attack: 0.001, decay: p.hatDecay, sustain: 0, release: 0.01 },
    harmonicity: p.hatHarmonicity, modulationIndex: p.hatModIndex, resonance: 4000, octaves: 1.5,
    volume: -16,
  }))
  closedHat.frequency.value = p.hatFreq
  closedHat.connect(hatHP)

  const openHat = keep(new Tone.MetalSynth({
    envelope: { attack: 0.001, decay: p.hatDecay * 7, sustain: 0.02, release: 0.2 },
    harmonicity: p.hatHarmonicity * 0.7, modulationIndex: p.hatModIndex * 0.6, resonance: 3500, octaves: 1.8,
    volume: -18,
  }))
  openHat.frequency.value = p.hatFreq * 0.85
  openHat.connect(hatHP)

  const cymbalHP = keep(new Tone.Filter({ frequency: 4000, type: 'highpass' })).connect(kitOut)
  const crash = keep(new Tone.MetalSynth({
    envelope: { attack: 0.001, decay: p.cymbalDecay, sustain: 0, release: 0.6 },
    harmonicity: 4.5, modulationIndex: 40, resonance: 5000, octaves: 2.2,
    volume: -22,
  }))
  crash.frequency.value = 300
  crash.connect(cymbalHP)

  const ride = keep(new Tone.MetalSynth({
    envelope: { attack: 0.001, decay: p.rideDecay, sustain: 0.04, release: 0.3 },
    harmonicity: 3.4, modulationIndex: 16, resonance: 6000, octaves: 1.6,
    volume: -20,
  }))
  ride.frequency.value = 520
  ride.connect(cymbalHP)

  // ── Toms: one pitched membrane voice ──────────────────────────────────────
  const tom = keep(new Tone.MembraneSynth({
    pitchDecay: 0.08, octaves: 3,
    oscillator: { type: 'sine' },
    envelope: { attack: 0.001, decay: 0.4, sustain: 0, release: 0.05 },
    volume: -8,
  })).connect(kitOut)

  const clamp = (v: number) => Math.max(0.02, Math.min(1, v))

  const trigger = (pitch: number, velocity: number, time: number): void => {
    const v = clamp(velocity)
    if (KICK.has(pitch)) {
      kick.triggerAttackRelease(p.kickNote, p.kickDecay, time, v)
      kickSub.triggerAttackRelease(p.subNote, p.subDecay, time, v)
      kickClick.triggerAttackRelease(0.02, time, v)
    } else if (SNARE.has(pitch)) {
      snareNoise.triggerAttackRelease(p.snareNoiseDecay, time, v)
      snareTone.triggerAttackRelease(p.snareToneFreq, 0.1, time, v * p.snareToneMix)
    } else if (pitch === CLAP) {
      clap.triggerAttackRelease(0.14, time, v)
      clap.triggerAttackRelease(0.1, time + 0.012, v * 0.7)   // second slap
    } else if (CLOSED_HAT.has(pitch)) {
      closedHat.triggerAttackRelease(p.hatDecay, time, v * 0.9)
    } else if (pitch === OPEN_HAT) {
      openHat.triggerAttackRelease(p.hatDecay * 7, time, v * 0.85)
    } else if (CRASH.has(pitch)) {
      crash.triggerAttackRelease(p.cymbalDecay, time, v * 0.8)
    } else if (RIDE.has(pitch)) {
      ride.triggerAttackRelease(p.rideDecay, time, v * 0.85)
    } else if (TOM_NOTE[pitch]) {
      tom.triggerAttackRelease(TOM_NOTE[pitch], 0.35, time, v)
    } else {
      closedHat.triggerAttackRelease(p.hatDecay, time, v * 0.7)   // unknown perc → tick
    }
  }

  return { trigger, nodes }
}
