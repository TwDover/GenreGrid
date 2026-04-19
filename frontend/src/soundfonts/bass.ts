import * as Tone from 'tone'
import { getMasterCompressor } from './loader'

const STYLE_TO_INSTRUMENT: Record<string, string> = {
  jazz:           'acoustic_bass',
  bossa_nova:     'acoustic_bass',
  latin_jazz:     'acoustic_bass',
  boom_bap:       'acoustic_bass',
  cumbia:         'acoustic_bass',
  cinematic:      'acoustic_bass',
  epic_orchestral:'acoustic_bass',
  lofi:           'fretless_bass',
  cloud_rap:      'fretless_bass',
  ambient:        'fretless_bass',
  dark_ambient:   'fretless_bass',
  funk:           'slap_bass_1',
  soul:           'electric_bass_finger',
  rnb:            'electric_bass_finger',
  trap_soul:      'electric_bass_finger',
  afrobeats:      'electric_bass_finger',
  dancehall:      'electric_bass_finger',
  dark_trap:      'electric_bass_pick',
  drill:          'electric_bass_pick',
  house:          'synth_bass_1',
  techno:         'synth_bass_1',
  synthwave:      'synth_bass_1',
  drum_and_bass:  'synth_bass_1',
  future_bass:    'synth_bass_1',
  reggaeton:      'synth_bass_1',
  jersey_club:    'synth_bass_1',
}
const DEFAULT_INSTRUMENT = 'electric_bass_finger'

const BASS_SAMPLE_MAP: Record<string, string> = {
  A1: 'A1.mp3', C2: 'C2.mp3', E2: 'E2.mp3', G2: 'G2.mp3',
  A2: 'A2.mp3', C3: 'C3.mp3', E3: 'E3.mp3', G3: 'G3.mp3', A3: 'A3.mp3',
}

// Warm instruments get a gentle low-pass to smooth the top end
const WARM_INSTRUMENTS = new Set(['acoustic_bass', 'fretless_bass'])

function buildBassFx(inst: string, comp: Tone.Compressor): Tone.ToneAudioNode {
  if (WARM_INSTRUMENTS.has(inst)) {
    const filter = new Tone.Filter({ frequency: 2200, type: 'lowpass', rolloff: -12 }).connect(comp)
    return filter
  }
  return comp
}

const bassCache = new Map<string, Promise<Tone.Sampler>>()

export function getBassSampler(styleId?: string): Promise<Tone.Sampler> {
  const inst = (styleId && STYLE_TO_INSTRUMENT[styleId]) ?? DEFAULT_INSTRUMENT
  if (bassCache.has(inst)) return bassCache.get(inst)!

  const comp = getMasterCompressor()
  const fxInput = buildBassFx(inst, comp)

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
