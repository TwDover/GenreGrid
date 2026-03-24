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

async function getSharedReverb(): Promise<Tone.Reverb> {
  if (reverb) return reverb
  const comp = getMasterCompressor()
  const r = new Tone.Reverb({ decay: 1.6, wet: 0.22 })
  await r.generate()
  r.connect(comp)
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
