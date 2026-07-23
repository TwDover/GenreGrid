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
import { getMelodicBus } from './loader'
import { LayeredSampler, loadLayeredSampler } from './layeredSampler'

// Per-part melodic voices come from the instrument registry (served via
// /styles → voices.{chords,melody,arpeggio}, read with voiceFor()). This module
// loads a sample set by voice id via getMelodicSamplerById; the registry is the
// single source of truth (see docs/instrument-identity-design.md).

const MELODIC_SAMPLE_MAP: Record<string, string> = {
  A2: 'A2.mp3', C3: 'C3.mp3', E3: 'E3.mp3', G3: 'G3.mp3',
  A3: 'A3.mp3', C4: 'C4.mp3', E4: 'E4.mp3', G4: 'G4.mp3',
  A4: 'A4.mp3', C5: 'C5.mp3', E5: 'E5.mp3', G5: 'G5.mp3',
  A5: 'A5.mp3',
}

// Voices with a confirmed-license (CC0 / CC-BY) sample set on disk. Only these load
// a sampler; every other voice is synthesized. The old MusyngKite-derived sets
// (electric pianos, clavinet, accordion, organ, nylon guitar, strings) were removed
// for licensing reasons — see docs/LICENSE_AUDIT.md — so they fall back to synths.
const INSTRUMENT_VOLUME: Record<string, number> = {
  vibraphone: -6,   // VCSL CC0, velocity-layered (peak-normalised → quieter than the old set)
}
const DEFAULT_VOLUME = -6

// ---------------------------------------------------------------------------
// Per-instrument effects chains
// Each returns the node the sampler should connect to; the chain tail connects
// to the melodic submix bus. Reverb instances are awaited so their IR is ready
// before playback starts.
// ---------------------------------------------------------------------------
async function buildFxChain(inst: string, out: Tone.ToneAudioNode): Promise<Tone.ToneAudioNode> {
  switch (inst) {

    case 'vibraphone': {
      // Short room reverb + light chorus for shimmer
      const reverb = new Tone.Reverb({ decay: 1.2, wet: 0.28 })
      await reverb.generate()
      reverb.connect(out)
      const chorus = new Tone.Chorus({ frequency: 2, depth: 0.25, wet: 0.18 }).connect(reverb)
      chorus.start()
      return chorus
    }

    default: {
      // Fallback: gentle verb for anything not specifically handled
      const reverb = new Tone.Reverb({ decay: 1.1, wet: 0.15 })
      await reverb.generate()
      reverb.connect(out)
      return reverb
    }
  }
}

// Cache: instrument name → promise resolving to the loaded sampler
const melodicCache = new Map<string, Promise<LayeredSampler>>()
// Cache: instrument name → promise resolving to the fx input node
const fxCache = new Map<string, Promise<Tone.ToneAudioNode>>()

// Voice ids that have real sample sets on disk (keys of INSTRUMENT_VOLUME).
// The instrument registry's playback_voice values reference these; anything
// else ("melody_lead", "pad_synth"…) is a synth family built in useMidiPlayer.
export const SAMPLED_VOICES = new Set(Object.keys(INSTRUMENT_VOLUME))

/** Load a melodic sampler by voice id (instrument-registry playback_voice).
 *  Returns null for non-sampled voices — callers fall back to synth voices. */
export function getMelodicSamplerById(inst: string): Promise<LayeredSampler> | null {
  if (!SAMPLED_VOICES.has(inst)) return null

  if (melodicCache.has(inst)) return melodicCache.get(inst)!

  if (!fxCache.has(inst)) {
    fxCache.set(inst, buildFxChain(inst, getMelodicBus()))
  }
  const fxPromise = fxCache.get(inst)!

  const promise = fxPromise.then(async (fxInput) => {
    const sampler = await loadLayeredSampler({
      baseUrl: `/samples/melodic/${inst}/`,
      legacyUrls: MELODIC_SAMPLE_MAP,
      volume: INSTRUMENT_VOLUME[inst] ?? DEFAULT_VOLUME,
    })
    sampler.connect(fxInput)
    return sampler
  })

  melodicCache.set(inst, promise)
  return promise
}

