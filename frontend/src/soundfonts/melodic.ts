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
// a sampler; every other voice is synthesized. The old MusyngKite-derived sets were
// removed for licensing reasons (docs/LICENSE_AUDIT.md); these are re-sourced
// replacements built by scripts/build_velocity_samples.py, which also records where
// each one came from. Levels are hand-set because every set is peak-normalised per
// note, so the source's own loudness is gone by the time it gets here.
//
// Still synthesized for want of a redistributable source: clavinet, drawbar_organ,
// accordion, acoustic_guitar_nylon.
const INSTRUMENT_VOLUME: Record<string, number> = {
  vibraphone: -6,          // VCSL CC0
  electric_piano_1: -8,    // Hohner Pianet T (CC-BY) standing in for a Rhodes
  electric_piano_2: -8,    // Wurlitzer EP200 (CC-BY) — the real thing for this voice
  string_ensemble_1: -12,  // VSCO 2 CE (CC0); sustained + stacked, so it needs the room
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

    case 'electric_piano_1': {
      // Rhodes voice: chorus is what makes a suitcase EP sound like one.
      const reverb = new Tone.Reverb({ decay: 1.4, wet: 0.2 })
      await reverb.generate()
      reverb.connect(out)
      const chorus = new Tone.Chorus({ frequency: 0.8, depth: 0.4, wet: 0.3 }).connect(reverb)
      chorus.start()
      return chorus
    }

    case 'electric_piano_2': {
      // Wurlitzer voice: its signature is the amp's tremolo, not chorus.
      const reverb = new Tone.Reverb({ decay: 1.2, wet: 0.16 })
      await reverb.generate()
      reverb.connect(out)
      const tremolo = new Tone.Tremolo({ frequency: 5.5, depth: 0.35, wet: 0.45 }).connect(reverb)
      tremolo.start()
      return tremolo
    }

    case 'string_ensemble_1': {
      // A section is heard in a hall; the long tail is most of the sound.
      const reverb = new Tone.Reverb({ decay: 2.8, wet: 0.35 })
      await reverb.generate()
      reverb.connect(out)
      return reverb
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

// Cache key: "<part>:<voice id>" → promise resolving to the loaded sampler/fx
// chain. Keyed per PART, not just voice id: two different parts (e.g. chords
// and melody) can independently resolve to the same sampled voice, and each
// needs its own instance + fx chain so a per-part volume/pan insert (roadmap
// 9.3) upstream of it actually isolates that part's audio.
const melodicCache = new Map<string, Promise<LayeredSampler>>()
const fxCache = new Map<string, Promise<Tone.ToneAudioNode>>()

// Voice ids that have real sample sets on disk (keys of INSTRUMENT_VOLUME).
// The instrument registry's playback_voice values reference these; anything
// else ("melody_lead", "pad_synth"…) is a synth family built in useMidiPlayer.
export const SAMPLED_VOICES = new Set(Object.keys(INSTRUMENT_VOLUME))

/** Load a melodic sampler by voice id (instrument-registry playback_voice) for
 *  a given part, connecting its fx chain to `out`. Returns null for non-sampled
 *  voices — callers fall back to synth voices. */
export function getMelodicSamplerById(inst: string, part: string, out: Tone.ToneAudioNode): Promise<LayeredSampler> | null {
  if (!SAMPLED_VOICES.has(inst)) return null

  const key = `${part}:${inst}`
  if (melodicCache.has(key)) return melodicCache.get(key)!

  if (!fxCache.has(key)) {
    fxCache.set(key, buildFxChain(inst, out))
  }
  const fxPromise = fxCache.get(key)!

  const promise = fxPromise.then(async (fxInput) => {
    const sampler = await loadLayeredSampler({
      baseUrl: `/samples/melodic/${inst}/`,
      legacyUrls: MELODIC_SAMPLE_MAP,
      volume: INSTRUMENT_VOLUME[inst] ?? DEFAULT_VOLUME,
    })
    sampler.connect(fxInput)
    return sampler
  })

  melodicCache.set(key, promise)
  return promise
}

