import * as Tone from 'tone'
import { getDrumBus } from './loader'

const STYLE_TO_KIT: Record<string, string> = {
  // Acoustic kit — live drum feel
  jazz:            'acoustic-kit',
  bossa_nova:      'acoustic-kit',
  latin_jazz:      'acoustic-kit',
  samba:           'acoustic-kit',
  afrobeats:       'acoustic-kit',
  afropop:         'acoustic-kit',
  cumbia:          'acoustic-kit',
  epic_orchestral: 'acoustic-kit',
  cinematic:       'acoustic-kit',
  // LinnDrum — classic vintage machine; punchy with natural decay
  soul:            'LINN',
  rnb:             'LINN',
  funk:            'LINN',
  // KPR77 — mellow, dusty; perfect for lo-fi and atmospheric
  lofi:            'KPR77',
  cloud_rap:       'KPR77',
  ambient:         'KPR77',
  dark_ambient:    'KPR77',
  // Roland R-8 — clean, digital punch; dembow/riddim patterns
  dancehall:       'R8',
  reggaeton:       'R8',
  baile_funk:      'R8',
  // Breakbeats — hip-hop sample chops
  boom_bap:        'breakbeat8',
  trap_soul:       'breakbeat8',
  dark_trap:       'breakbeat13',
  drill:           'breakbeat13',
  // Electronic / club — Techno kit (tight, synthetic)
  house:           'Techno',
  techno:          'Techno',
  drum_and_bass:   'Techno',
  future_bass:     'Techno',
  synthwave:       'Techno',
  jersey_club:     'Techno',
  // grime + hyperpop use SYNTH_STYLES → makeSynthDrums(), no kit loaded
}
const DEFAULT_KIT = 'acoustic-kit'

// Map each kit to a synthesized-drum character preset (see synthDrums.ts).
const KIT_TO_CHARACTER: Record<string, import('./synthDrums').DrumCharacter> = {
  'acoustic-kit': 'acoustic',
  LINN:           'punchy',
  KPR77:          'lofi',
  CR78:           'vintage',
  R8:             'digital',
  Techno:         'techno',
  breakbeat8:     'breakbeat',
  breakbeat13:    'breakbeat',
}

/** Resolve the synthesized-drum character for a style (used by the live player). */
export function drumCharacterForStyle(styleId?: string): import('./synthDrums').DrumCharacter {
  // Styles without a sampled kit (grime, hyperpop) were pure-synthesis before —
  // give them a hard electronic character.
  const kit = (styleId && STYLE_TO_KIT[styleId]) ?? (styleId ? 'Techno' : DEFAULT_KIT)
  return KIT_TO_CHARACTER[kit] ?? 'acoustic'
}

// Kits that get light room reverb (acoustic sources benefit; electronic stays dry)
const REVERB_KITS = new Set(['acoustic-kit', 'LINN'])
const KIT_REVERB_PARAMS: Record<string, { decay: number; wet: number }> = {
  'acoustic-kit': { decay: 0.7, wet: 0.16 },
  'LINN':         { decay: 0.4, wet: 0.10 },
}

export const DRUM_PITCH_TO_SAMPLE: Record<number, string> = {
  35: 'kick',  36: 'kick',
  38: 'snare', 39: 'snare', 40: 'snare',
  41: 'tom3',  43: 'tom3',
  45: 'tom2',  47: 'tom2',
  48: 'tom1',  50: 'tom1',
  42: 'hihat', 44: 'hihat',
  46: 'hihat_open',
  49: 'crash', 52: 'crash', 55: 'crash', 57: 'crash',
  51: 'ride',  53: 'ride',  59: 'ride',
}

const kitCache = new Map<string, Promise<Tone.Players>>()

async function buildDrumFx(kitName: string, out: Tone.ToneAudioNode): Promise<Tone.ToneAudioNode> {
  if (REVERB_KITS.has(kitName)) {
    const params = KIT_REVERB_PARAMS[kitName]
    const reverb = new Tone.Reverb({ decay: params.decay, wet: params.wet })
    await reverb.generate()
    reverb.connect(out)
    return reverb
  }
  // Electronic kits: connect directly (dry)
  return out
}

export function getDrumKit(styleId?: string): Promise<Tone.Players> {
  const kitName = (styleId && STYLE_TO_KIT[styleId]) ?? DEFAULT_KIT
  if (kitCache.has(kitName)) return kitCache.get(kitName)!

  const bus = getDrumBus()
  const base = `/samples/drums/${kitName}/`

  const promise = buildDrumFx(kitName, bus).then(
    (fxInput) =>
      new Promise<Tone.Players>((resolve, reject) => {
        const players = new Tone.Players(
          {
            kick:       base + 'kick.mp3',
            snare:      base + 'snare.mp3',
            hihat:      base + 'hihat.mp3',
            // Open hihat/crash/ride: dedicated files where available; download_samples.py
            // creates these from the hihat as a fallback for kits without real articulations.
            hihat_open: base + 'hihat_open.mp3',
            crash:      base + 'crash.mp3',
            ride:       base + 'ride.mp3',
            tom1:       base + 'tom1.mp3',
            tom2:       base + 'tom2.mp3',
            tom3:       base + 'tom3.mp3',
          },
          () => resolve(players),
        ).connect(fxInput)
        setTimeout(() => reject(new Error(`Drum kit "${kitName}" load timeout`)), 15_000)
      }),
  )

  kitCache.set(kitName, promise)
  return promise
}
