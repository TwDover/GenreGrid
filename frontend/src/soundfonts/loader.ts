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

// Salamander Grand Piano — bundled locally under public/samples/piano/ (served by
// the renderer's static server) so the flagship piano works fully offline and
// doesn't fetch from a third-party host at runtime. Same sample set as the Tone.js
// examples; served identically to the other instruments' /samples/... sets.
const BASE_URL = '/samples/piano/'

const SAMPLE_MAP: Record<string, string> = {
  A0: 'A0.mp3',   C1: 'C1.mp3',   'D#1': 'Ds1.mp3', 'F#1': 'Fs1.mp3',
  A1: 'A1.mp3',   C2: 'C2.mp3',   'D#2': 'Ds2.mp3', 'F#2': 'Fs2.mp3',
  A2: 'A2.mp3',   C3: 'C3.mp3',   'D#3': 'Ds3.mp3', 'F#3': 'Fs3.mp3',
  A3: 'A3.mp3',   C4: 'C4.mp3',   'D#4': 'Ds4.mp3', 'F#4': 'Fs4.mp3',
  A4: 'A4.mp3',   C5: 'C5.mp3',   'D#5': 'Ds5.mp3', 'F#5': 'Fs5.mp3',
  A5: 'A5.mp3',   C6: 'C6.mp3',   'D#6': 'Ds6.mp3', 'F#6': 'Fs6.mp3',
  A6: 'A6.mp3',   C7: 'C7.mp3',   'D#7': 'Ds7.mp3', 'F#7': 'Fs7.mp3',
  A7: 'A7.mp3',   C8: 'C8.mp3',
}

// Module-level singletons — created once, reused across all plays
let masterOut: Tone.Gain | null = null
let reverb: Tone.Reverb | null = null
let piano: Tone.Sampler | null = null
let loadPromise: Promise<Tone.Sampler> | null = null

// Master output node. This used to be a Tone.Compressor for mix glue, but a
// DynamicsCompressorNode renders SILENCE to the hardware on Linux packaged Electron —
// signal enters it (meters read it fine) yet nothing reaches the speakers, and since the
// entire mix routes through this one node, the whole app was silent on Linux (Win/Mac were
// unaffected). A plain Gain works on every platform, so the master is now a unity gain
// straight to the destination. (Kept the name to avoid touching every call site.)
export function getMasterCompressor(): Tone.Gain {
  if (masterOut) return masterOut
  masterOut = new Tone.Gain(1).toDestination()
  console.log(`[audio] master gain created (ctx=${Tone.getContext().state}, sr=${Tone.getContext().rawContext.sampleRate}) → toDestination`)
  return masterOut
}

// ── Submix buses ───────────────────────────────────────────────────────────
// Every instrument routes through its group bus before the master compressor,
// so the three groups can be balanced against each other. The synthesized drum
// kit sets its own per-voice levels internally, so this bus only needs a gentle
// trim to keep drums present without burying the harmonic parts. Tweak these
// three numbers to re-balance the whole app.
const DRUM_BUS_DB    = -5
const BASS_BUS_DB    = -3
const MELODIC_BUS_DB = 0

let drumBus: Tone.Gain<'decibels'> | null = null
let bassBus: Tone.Gain<'decibels'> | null = null
let melodicBus: Tone.Gain<'decibels'> | null = null
let melodicChorus: Tone.Chorus | null = null
let melodicDelay: Tone.FeedbackDelay | null = null

export function getDrumBus(): Tone.Gain<'decibels'> {
  if (!drumBus) drumBus = new Tone.Gain(DRUM_BUS_DB, 'decibels').connect(getMasterCompressor())
  return drumBus
}

export function getBassBus(): Tone.Gain<'decibels'> {
  if (!bassBus) bassBus = new Tone.Gain(BASS_BUS_DB, 'decibels').connect(getMasterCompressor())
  return bassBus
}

// The melodic bus carries ONE shared Chorus + FeedbackDelay for all harmonic voices
// (chords, melody, arp, pads, strings), instead of each voice building its own pair. That
// per-voice duplication was the biggest render cost after the drums; sharing it frees the
// audio thread so it doesn't underrun/glitch under a full arrangement's load.
//   voices → melodicBus(Gain) → chorus → delay → master
export function getMelodicBus(): Tone.Gain<'decibels'> {
  if (!melodicBus) {
    melodicDelay = new Tone.FeedbackDelay({ delayTime: '8n.', feedback: 0.22, wet: 0.12 }).connect(getMasterCompressor())
    melodicChorus = new Tone.Chorus({ frequency: 1.5, depth: 0.3, wet: 0.18 }).connect(melodicDelay)
    melodicChorus.start()
    melodicBus = new Tone.Gain(MELODIC_BUS_DB, 'decibels').connect(melodicChorus)
  }
  return melodicBus
}

// ── Sidechain pump ───────────────────────────────────────────────────────────
// Duck the melodic and bass buses briefly on each kick — the four-on-the-floor
// "pump" that makes electronic mixes breathe. Called from the drum scheduler at
// the kick's exact transport time; the buses recover before the next 8th note.
export function duckOnKick(time: number, depthDb = -7, releaseS = 0.22): void {
  const buses: Array<[Tone.Gain<'decibels'> | null, number]> = [
    [melodicBus, MELODIC_BUS_DB],
    [bassBus, BASS_BUS_DB],
  ]
  for (const [bus, baseDb] of buses) {
    if (!bus) continue
    bus.gain.cancelScheduledValues(time)
    bus.gain.setValueAtTime(baseDb + depthDb, time)
    bus.gain.linearRampToValueAtTime(baseDb, time + releaseS)
  }
}

// Restore bus levels after playback stops so the pump can't leave a duck behind.
export function resetBusLevels(): void {
  if (melodicBus) { melodicBus.gain.cancelScheduledValues(0); melodicBus.gain.value = MELODIC_BUS_DB }
  if (bassBus)    { bassBus.gain.cancelScheduledValues(0);    bassBus.gain.value = BASS_BUS_DB }
}

async function getSharedReverb(): Promise<Tone.Reverb> {
  if (reverb) return reverb
  const r = new Tone.Reverb({ decay: 1.6, wet: 0.22 })
  await r.generate()
  r.connect(getMelodicBus())      // piano is a melodic voice — route through its bus
  reverb = r
  return r
}

/**
 * Load the Salamander piano sampler once and cache it.
 * Subsequent calls return the cached instance immediately.
 */
export async function getPianoSampler(): Promise<Tone.Sampler> {
  if (piano) return piano
  if (loadPromise) return loadPromise

  loadPromise = getSharedReverb().then(
    (rv) =>
      new Promise<Tone.Sampler>((resolve, reject) => {
        const sampler = new Tone.Sampler({
          urls: SAMPLE_MAP,
          baseUrl: BASE_URL,
          volume: -6,
          onload: () => {
            piano = sampler
            resolve(sampler)
          },
          onerror: reject,
        }).connect(rv)
      }),
  )

  return loadPromise
}
