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

// Synth voice factories for live playback. As of roadmap 6.6 these are thin wrappers
// over `buildSynthFromPatch` (synthPatch.ts): each voice is now a serializable
// `SynthPatch` rendered by one pure factory, instead of a bespoke function per voice.
// The wrappers keep their original names/signatures so callers (useMidiPlayer.ts)
// don't change, and each builds the *same* Tone node graph as before — the migration
// is byte-identical, gated by patchToNodeSpec in synthPatch.test.ts. Each still
// registers every created node in the caller's `disposables` for cleanup(); the
// sampled voices stay in loader.ts.
import * as Tone from 'tone'
import { getMelodicBus, getBassBus } from './loader'
import {
  buildSynthFromPatch,
  PRESET_MELODY_LEAD_SOFT,
  PRESET_SYNTH_LEAD,
  PRESET_SYNTH_CHORDS,
  PRESET_ARP_PLUCK,
  PRESET_PAD,
  PRESET_STRINGS,
  PRESET_SYNTH_BASS,
  PRESET_LOFI,
} from './synthPatch'

// Melody lead — a dedicated, in-tune, articulate voice for the melodic LINE. Fast
// attack so every note reads, a tamed low-pass so it's not harsh; `soft` warms it
// (triangle, slower attack) for ambient/cinematic styles.
export function makeMelodyLead(soft: boolean, disposables: Tone.ToneAudioNode[], output: Tone.ToneAudioNode = getMelodicBus()): Tone.PolySynth {
  return buildSynthFromPatch(soft ? PRESET_MELODY_LEAD_SOFT : PRESET_SYNTH_LEAD, disposables, output) as Tone.PolySynth
}

// Synth comp: detuned/warm saw stack — deliberately darker than the lead so CHORDS
// don't collide with the melody timbre on electronic styles.
export function makeSynthChords(disposables: Tone.ToneAudioNode[], output: Tone.ToneAudioNode = getMelodicBus()): Tone.PolySynth {
  return buildSynthFromPatch(PRESET_SYNTH_CHORDS, disposables, output) as Tone.PolySynth
}

// Arp pluck: short, bright, decaying voice — gives the arpeggio its own identity.
export function makeArpPluck(disposables: Tone.ToneAudioNode[], output: Tone.ToneAudioNode = getMelodicBus()): Tone.PolySynth {
  return buildSynthFromPatch(PRESET_ARP_PLUCK, disposables, output) as Tone.PolySynth
}

// Pad: slow-attack triangle wash (ambient, cinematic, etc.)
export function makePad(disposables: Tone.ToneAudioNode[], output: Tone.ToneAudioNode = getMelodicBus()): Tone.PolySynth {
  return buildSynthFromPatch(PRESET_PAD, disposables, output) as Tone.PolySynth
}

// Strings ensemble: soft detuned-saw stack for the counter-melody part.
export function makeStrings(disposables: Tone.ToneAudioNode[], output: Tone.ToneAudioNode = getMelodicBus()): Tone.PolySynth {
  return buildSynthFromPatch(PRESET_STRINGS, disposables, output) as Tone.PolySynth
}

// Synth bass: sawtooth MonoSynth with a moving filter + portamento — routed to the
// dedicated bass bus (house/techno/dnb etc.).
export function makeSynthBass(disposables: Tone.ToneAudioNode[]): Tone.MonoSynth {
  return buildSynthFromPatch(PRESET_SYNTH_BASS, disposables, getBassBus()) as Tone.MonoSynth
}

// Lo-fi synth: warm triangle → bitcrusher → lowpass → vibrato.
export function makeLofiSynth(disposables: Tone.ToneAudioNode[], output: Tone.ToneAudioNode = getMelodicBus()): Tone.PolySynth {
  return buildSynthFromPatch(PRESET_LOFI, disposables, output) as Tone.PolySynth
}
