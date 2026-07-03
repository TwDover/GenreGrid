import * as Tone from 'tone'

// Salamander Grand Piano — same sample set used in Tone.js official examples
const BASE_URL = 'https://tonejs.github.io/audio/salamander/'

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
let compressor: Tone.Compressor | null = null
let reverb: Tone.Reverb | null = null
let piano: Tone.Sampler | null = null
let loadPromise: Promise<Tone.Sampler> | null = null

export function getMasterCompressor(): Tone.Compressor {
  if (compressor) return compressor
  compressor = new Tone.Compressor({ threshold: -18, ratio: 4, attack: 0.003, release: 0.1 }).toDestination()
  return compressor
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

export function getDrumBus(): Tone.Gain<'decibels'> {
  if (!drumBus) drumBus = new Tone.Gain(DRUM_BUS_DB, 'decibels').connect(getMasterCompressor())
  return drumBus
}

export function getBassBus(): Tone.Gain<'decibels'> {
  if (!bassBus) bassBus = new Tone.Gain(BASS_BUS_DB, 'decibels').connect(getMasterCompressor())
  return bassBus
}

export function getMelodicBus(): Tone.Gain<'decibels'> {
  if (!melodicBus) melodicBus = new Tone.Gain(MELODIC_BUS_DB, 'decibels').connect(getMasterCompressor())
  return melodicBus
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
