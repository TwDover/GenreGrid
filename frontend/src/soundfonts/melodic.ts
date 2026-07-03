import * as Tone from 'tone'
import { getMelodicBus } from './loader'

const STYLE_TO_INSTRUMENT: Record<string, string> = {
  // Rhodes electric piano — warm, classic; lo-fi hip-hop IS Rhodes
  lofi:        'electric_piano_1',
  soul:        'electric_piano_1',
  rnb:         'electric_piano_1',
  boom_bap:    'electric_piano_1',
  trap_soul:   'electric_piano_1',   // sampler used even though PAD_STYLES handles melodic synth
  afrobeats:   'electric_piano_1',
  dancehall:   'electric_piano_1',
  // Vibraphone — jazz/latin percussive shimmer
  jazz:        'vibraphone',
  latin_jazz:  'vibraphone',
  // Nylon guitar — bossa nova fingerpicked comp; samba cavaquinho proxy
  bossa_nova:  'acoustic_guitar_nylon',
  samba:       'acoustic_guitar_nylon',
  // Clavinet — punky funk keyboard (Superstition, Higher Ground)
  funk:        'clavinet',
  // Accordion — characteristic cumbia sound
  cumbia:      'accordion',
  // Drawbar organ — afropop rhythm guitar substitute (closest warm attack available)
  afropop:     'drawbar_organ',
  // Strings — orchestral/cinematic pads
  cinematic:      'string_ensemble_1',
  epic_orchestral:'string_ensemble_1',
  // Warm pad substitute for ambient (strings give the slow-attack pad feel in GM)
  ambient:     'string_ensemble_1',
  dark_ambient:'string_ensemble_1',
}

const MELODIC_SAMPLE_MAP: Record<string, string> = {
  A2: 'A2.mp3', C3: 'C3.mp3', E3: 'E3.mp3', G3: 'G3.mp3',
  A3: 'A3.mp3', C4: 'C4.mp3', E4: 'E4.mp3', G4: 'G4.mp3',
  A4: 'A4.mp3', C5: 'C5.mp3', E5: 'E5.mp3', G5: 'G5.mp3',
  A5: 'A5.mp3',
}

const INSTRUMENT_VOLUME: Record<string, number> = {
  vibraphone:            -3,
  acoustic_guitar_nylon: -2,
  clavinet:              -8,
  accordion:             -5,
  string_ensemble_1:     -3,
  electric_piano_1:      -5,
  electric_piano_2:      -6,
  drawbar_organ:         -7,
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

    case 'string_ensemble_1': {
      // Long hall reverb — lush orchestral pad sound
      const reverb = new Tone.Reverb({ decay: 2.8, wet: 0.38 })
      await reverb.generate()
      reverb.connect(out)
      return reverb
    }

    case 'vibraphone': {
      // Short room reverb + light chorus for shimmer
      const reverb = new Tone.Reverb({ decay: 1.2, wet: 0.28 })
      await reverb.generate()
      reverb.connect(out)
      const chorus = new Tone.Chorus({ frequency: 2, depth: 0.25, wet: 0.18 }).connect(reverb)
      chorus.start()
      return chorus
    }

    case 'acoustic_guitar_nylon': {
      // Warm room reverb — adds natural space without washing out the attack
      const reverb = new Tone.Reverb({ decay: 1.5, wet: 0.22 })
      await reverb.generate()
      reverb.connect(out)
      return reverb
    }

    case 'electric_piano_1': {
      // Classic Rhodes treatment: chorus for movement + short verb for bloom
      const reverb = new Tone.Reverb({ decay: 1.4, wet: 0.20 })
      await reverb.generate()
      reverb.connect(out)
      const chorus = new Tone.Chorus({ frequency: 3, depth: 0.35, wet: 0.22 }).connect(reverb)
      chorus.start()
      return chorus
    }

    case 'electric_piano_2': {
      // DX7 is naturally bright — minimal verb, no chorus
      const reverb = new Tone.Reverb({ decay: 0.9, wet: 0.14 })
      await reverb.generate()
      reverb.connect(out)
      return reverb
    }

    case 'clavinet': {
      // Phaser for that wah-funk movement; stays dry and punchy (no reverb)
      const phaser = new Tone.Phaser({ frequency: 2.5, octaves: 3, wet: 0.45 }).connect(out)
      return phaser
    }

    case 'drawbar_organ': {
      // Rotary / Leslie simulator via chorus
      const chorus = new Tone.Chorus({ frequency: 3.5, depth: 0.55, wet: 0.5 }).connect(out)
      chorus.start()
      return chorus
    }

    case 'accordion': {
      // Light room verb — keeps the attack crisp
      const reverb = new Tone.Reverb({ decay: 1.0, wet: 0.16 })
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

// Cache: instrument name → promise resolving to the loaded Tone.Sampler
const melodicCache = new Map<string, Promise<Tone.Sampler>>()
// Cache: instrument name → promise resolving to the fx input node
const fxCache = new Map<string, Promise<Tone.ToneAudioNode>>()

export function getMelodicSampler(styleId?: string): Promise<Tone.Sampler> | null {
  const inst = styleId ? STYLE_TO_INSTRUMENT[styleId] : undefined
  if (!inst) return null

  if (melodicCache.has(inst)) return melodicCache.get(inst)!

  // Reuse or create the fx chain for this instrument (routed to the melodic bus)
  if (!fxCache.has(inst)) {
    fxCache.set(inst, buildFxChain(inst, getMelodicBus()))
  }
  const fxPromise = fxCache.get(inst)!

  const promise = fxPromise.then(
    (fxInput) =>
      new Promise<Tone.Sampler>((resolve, reject) => {
        const sampler = new Tone.Sampler({
          urls: MELODIC_SAMPLE_MAP,
          baseUrl: `/samples/melodic/${inst}/`,
          volume: INSTRUMENT_VOLUME[inst] ?? DEFAULT_VOLUME,
          onload: () => resolve(sampler),
          onerror: reject,
        }).connect(fxInput)
      }),
  )

  melodicCache.set(inst, promise)
  return promise
}

export function getMelodicInstrumentName(styleId?: string): string | null {
  return (styleId && STYLE_TO_INSTRUMENT[styleId]) ?? null
}
