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

// The per-style bass sample set now comes from the instrument registry: each
// style's `instrumentation.bass` resolves to an instrument whose `playback_voice`
// is one of these sample-dir names (served via /styles → voices.bass, read with
// voiceFor()). This module just loads the sample set it's handed — the registry
// is the single source of truth (see docs/instrument-identity-design.md).
const DEFAULT_INSTRUMENT = 'electric_bass_finger'

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

const bassCache = new Map<string, Promise<Tone.Sampler>>()

export function getBassSampler(voice?: string | null): Promise<Tone.Sampler> {
  const inst = voice ?? DEFAULT_INSTRUMENT
  if (bassCache.has(inst)) return bassCache.get(inst)!

  const fxInput = buildBassFx(inst, getBassBus())

  const promise = new Promise<Tone.Sampler>((resolve, reject) => {
    const sampler = new Tone.Sampler({
      urls: BASS_SAMPLE_MAP,
      baseUrl: `/samples/bass/${inst}/`,
      volume: -4,
      onload: () => resolve(sampler),
      onerror: reject,
    }).connect(fxInput)
  })

  bassCache.set(inst, promise)
  return promise
}
