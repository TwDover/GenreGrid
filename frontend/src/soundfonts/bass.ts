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
import { getBassBus } from './loader'
import { LayeredSampler, loadLayeredSampler } from './layeredSampler'

// The per-style bass sample set now comes from the instrument registry: each
// style's `instrumentation.bass` resolves to an instrument whose `playback_voice`
// is one of these sample-dir names (served via /styles → voices.bass, read with
// voiceFor()). This module just loads the sample set it's handed — the registry
// is the single source of truth (see docs/instrument-identity-design.md).
const DEFAULT_INSTRUMENT = 'electric_bass_finger'

// Bass voices with a confirmed-license, velocity-layered sample set on disk. The
// MusyngKite-derived sets were removed for licensing reasons (docs/LICENSE_AUDIT.md);
// these replacements are re-sourced from CC0 libraries by scripts/build_velocity_samples.py.
//
// synth_bass_1 is deliberately absent: it IS a synth, so the app's own oscillator
// is both more honest and more tweakable than a frozen sample of someone else's.
export const SAMPLED_BASS_VOICES = new Set<string>([
  'acoustic_bass',
  'electric_bass_finger',
  'electric_bass_pick',
  'fretless_bass',
  'slap_bass_1',
])

// Voice id → sample directory. Only needed where a voice has no set of its own:
// no CC0 slap-bass library exists, so slap borrows the fingered Jazz Bass — the
// nearest sampled instrument, the same substitution the registry already makes
// for marimba → vibraphone. Unlisted voices use a directory of their own name.
export const BASS_SAMPLE_DIR: Record<string, string> = {
  slap_bass_1: 'electric_bass_finger',
}

const BASS_SAMPLE_MAP: Record<string, string> = {
  A1: 'A1.mp3', C2: 'C2.mp3', E2: 'E2.mp3', G2: 'G2.mp3',
  A2: 'A2.mp3', C3: 'C3.mp3', E3: 'E3.mp3', G3: 'G3.mp3', A3: 'A3.mp3',
}

// Warm instruments get a gentle low-pass to smooth the top end
const WARM_INSTRUMENTS = new Set(['acoustic_bass', 'fretless_bass'])

function buildBassFx(inst: string, out: Tone.ToneAudioNode): Tone.ToneAudioNode {
  if (WARM_INSTRUMENTS.has(inst)) {
    const filter = new Tone.Filter({ frequency: 2200, type: 'lowpass', rolloff: -12 }).connect(out)
    return filter
  }
  return out
}

const bassCache = new Map<string, Promise<LayeredSampler>>()

export function getBassSampler(voice?: string | null): Promise<LayeredSampler> {
  const inst = voice ?? DEFAULT_INSTRUMENT
  if (bassCache.has(inst)) return bassCache.get(inst)!

  const fxInput = buildBassFx(inst, getBassBus())

  const promise = loadLayeredSampler({
    baseUrl: `/samples/bass/${BASS_SAMPLE_DIR[inst] ?? inst}/`,
    legacyUrls: BASS_SAMPLE_MAP,
    volume: -4,
  }).then((sampler) => {
    sampler.connect(fxInput)
    return sampler
  })

  bassCache.set(inst, promise)
  return promise
}
