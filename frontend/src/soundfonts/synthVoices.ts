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

// Synth voice factories for live playback — each builds a Tone voice + its FX
// nodes and registers every created node in the caller's `disposables` array so
// the player's cleanup() disposes them. Split out of useMidiPlayer.ts (they sit
// next to makeSynthKit in synthDrums.ts); the sampled voices stay in loader.ts.
import * as Tone from 'tone'
import { getMelodicBus, getBassBus } from './loader'

// Melody lead — a dedicated, in-tune, articulate voice for the melodic LINE.
// Replaces two bad melody voices: the harsh heavily-chorused sawtooth (which
// wavered out of tune) and the pad (0.8 s attack, so fast melody notes never
// spoke). Fast attack so every note reads, a tamed low-pass so it's not harsh,
// and only a whisper of chorus so it stays in tune. `soft` warms it and adds
// space for ambient/cinematic styles.
export function makeMelodyLead(soft: boolean, disposables: Tone.ToneAudioNode[], output: Tone.ToneAudioNode = getMelodicBus()): Tone.PolySynth {
  // Chorus + delay now live once on the shared melodic bus (see getMelodicBus).
  const filter = new Tone.Filter({ frequency: soft ? 3000 : 3800, type: 'lowpass', rolloff: -12, Q: 0.8 }).connect(output)
  const synth = new Tone.PolySynth(Tone.Synth, {
    oscillator: soft ? { type: 'triangle' } : { type: 'sawtooth' },
    envelope: soft
      ? { attack: 0.03, decay: 0.2,  sustain: 0.75, release: 0.8 }
      : { attack: 0.008, decay: 0.15, sustain: 0.65, release: 0.3 },
    volume: soft ? -9 : -10,
  }).connect(filter)
  disposables.push(filter, synth)
  return synth
}

// Synth comp: detuned/warm saw stack, slower attack, rolled-off highs.
// Deliberately darker than makeSynthLead so CHORDS don't collide with the melody
// timbre on electronic styles (previously both used the same sawtooth lead).
export function makeSynthChords(disposables: Tone.ToneAudioNode[], output: Tone.ToneAudioNode = getMelodicBus()): Tone.PolySynth {
  const lp = new Tone.Filter({ frequency: 2600, type: 'lowpass', rolloff: -12 }).connect(output)
  const synth = new Tone.PolySynth(Tone.Synth, {
    oscillator: { type: 'fatsawtooth', count: 3, spread: 22 },
    envelope: { attack: 0.06, decay: 0.25, sustain: 0.65, release: 0.6 },
    volume: -15,
  }).connect(lp)
  disposables.push(lp, synth)
  return synth
}

// Arp pluck: short, bright, decaying voice with a synced delay tail. Gives the
// arpeggio part its own identity instead of doubling the chord/lead timbre.
export function makeArpPluck(disposables: Tone.ToneAudioNode[], output: Tone.ToneAudioNode = getMelodicBus()): Tone.PolySynth {
  const lp = new Tone.Filter({ frequency: 4200, type: 'lowpass', rolloff: -12 }).connect(output)
  const synth = new Tone.PolySynth(Tone.Synth, {
    oscillator: { type: 'triangle' },
    envelope: { attack: 0.004, decay: 0.18, sustain: 0.0, release: 0.25 },
    volume: -12,
  }).connect(lp)
  disposables.push(lp, synth)
  return synth
}

// Pad: slow-attack triangle + long feedback delay (ambient, cinematic, etc.)
export function makePad(disposables: Tone.ToneAudioNode[], output: Tone.ToneAudioNode = getMelodicBus()): Tone.PolySynth {
  const synth = new Tone.PolySynth(Tone.Synth, {
    oscillator: { type: 'triangle' },
    envelope: { attack: 0.8, decay: 0.3, sustain: 0.7, release: 2.0 },
    volume: -10,
  }).connect(output)
  disposables.push(synth)
  return synth
}

// Strings ensemble: soft detuned-saw stack for the counter-melody part —
// articulate enough to read as a line, slow and dark enough to sit behind
// the lead instead of competing with it.
export function makeStrings(disposables: Tone.ToneAudioNode[], output: Tone.ToneAudioNode = getMelodicBus()): Tone.PolySynth {
  const lp = new Tone.Filter({ frequency: 2400, type: 'lowpass', rolloff: -12 }).connect(output)
  const synth = new Tone.PolySynth(Tone.Synth, {
    oscillator: { type: 'fatsawtooth', count: 3, spread: 14 },
    envelope: { attack: 0.12, decay: 0.3, sustain: 0.8, release: 1.2 },
    volume: -14,
  }).connect(lp)
  disposables.push(lp, synth)
  return synth
}

// Synth bass: sawtooth MonoSynth with portamento — house/techno/dnb etc.
export function makeSynthBass(disposables: Tone.ToneAudioNode[]): Tone.MonoSynth {
  const comp = getBassBus()
  const bass = new Tone.MonoSynth({
    oscillator: { type: 'sawtooth' },
    filter: { Q: 2.5, type: 'lowpass', rolloff: -24 },
    envelope: { attack: 0.01, decay: 0.08, sustain: 0.9, release: 0.3 },
    filterEnvelope: { attack: 0.04, decay: 0.2, sustain: 0.5, release: 0.3, baseFrequency: 180, octaves: 2.6 },
    portamento: 0.035,
    volume: -3,
  }).connect(comp)
  disposables.push(bass)
  return bass
}

// Lo-fi synth: warm triangle → bitcrusher → lowpass → vibrato → compressor
export function makeLofiSynth(disposables: Tone.ToneAudioNode[], output: Tone.ToneAudioNode = getMelodicBus()): Tone.PolySynth {
  const vibrato = new Tone.Vibrato({ frequency: 2.5, depth: 0.04, wet: 1 }).connect(output)
  const lp = new Tone.Filter({ frequency: 5500, type: 'lowpass' }).connect(vibrato)
  const crusher = new Tone.BitCrusher({ bits: 10 }).connect(lp)
  const synth = new Tone.PolySynth(Tone.Synth, {
    oscillator: { type: 'triangle' },
    envelope: { attack: 0.04, decay: 0.2, sustain: 0.6, release: 1.2 },
    volume: -4,
  }).connect(crusher)
  disposables.push(vibrato, lp, crusher, synth)
  return synth
}
