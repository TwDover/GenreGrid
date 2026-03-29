import { ref } from 'vue'
import * as Tone from 'tone'
import { Midi } from '@tonejs/midi'
import { downloadUrl } from '../services/api'
import { getPianoSampler, getMasterCompressor } from '../soundfonts/loader'
import { getDrumKit, DRUM_PITCH_TO_SAMPLE } from '../soundfonts/drums'
import { getBassSampler } from '../soundfonts/bass'
import { getMelodicSampler } from '../soundfonts/melodic'

export interface ParsedNote {
  midi: number
  time: number
  duration: number
  velocity: number
  isPercussion: boolean
}

export interface MidiData {
  notes: ParsedNote[]
  duration: number
}

// Style groups for synth/pad/lofi fallbacks (no bundled samples)
const SYNTH_STYLES = new Set([
  'house', 'techno', 'drum_and_bass', 'synthwave', 'future_bass',
  'drill', 'jersey_club', 'reggaeton', 'dancehall', 'cumbia', 'afrobeats',
])
const PAD_STYLES = new Set(['ambient', 'dark_ambient', 'epic_orchestral', 'cinematic'])
const LOFI_STYLES = new Set(['lofi', 'cloud_rap'])

// Global so only one track plays at a time
const currentlyPlaying = ref<string | null>(null)
const isLoading = ref(false)

// Master volume: 0–100 maps to dB via gainToDb
const volume = ref(80)

function applyVolume(v: number) {
  Tone.getDestination().volume.value = v === 0 ? -Infinity : Tone.gainToDb(v / 100)
}
// Volume is applied inside toggle() after Tone.start() — calling applyVolume here
// would create the AudioContext at import time, which browsers block before a user gesture.

// Cache parsed MIDI data per URL so the piano roll persists after stop
const midiStore = ref<Record<string, MidiData>>({})

let scheduledParts: Tone.Part[] = []
// Per-play disposables — samplers and synths that are NOT globally cached
let disposables: Tone.ToneAudioNode[] = []

function cleanup() {
  Tone.getTransport().stop()
  Tone.getTransport().cancel()
  scheduledParts.forEach(p => p.dispose())
  disposables.forEach(d => d.dispose())
  scheduledParts = []
  disposables = []
  currentlyPlaying.value = null
}

// Synth lead: sawtooth + chorus + ping-pong delay (house, techno, synthwave, etc.)
function makeSynthLead(): Tone.PolySynth {
  const comp = getMasterCompressor()
  const delay = new Tone.PingPongDelay({ delayTime: '8n', feedback: 0.2, wet: 0.12 }).connect(comp)
  const chorus = new Tone.Chorus({ frequency: 3, depth: 0.4, wet: 0.25 }).connect(delay)
  chorus.start()
  const synth = new Tone.PolySynth(Tone.Synth, {
    oscillator: { type: 'sawtooth' },
    envelope: { attack: 0.01, decay: 0.12, sustain: 0.8, release: 0.4 },
    volume: -10,
  }).connect(chorus)
  disposables.push(delay, chorus, synth)
  return synth
}

// Pad: slow-attack triangle + long feedback delay (ambient, cinematic, etc.)
function makePad(): Tone.PolySynth {
  const comp = getMasterCompressor()
  const delay = new Tone.FeedbackDelay({ delayTime: '4n', feedback: 0.4, wet: 0.3 }).connect(comp)
  const synth = new Tone.PolySynth(Tone.Synth, {
    oscillator: { type: 'triangle' },
    envelope: { attack: 0.8, decay: 0.3, sustain: 0.7, release: 2.0 },
    volume: -10,
  }).connect(delay)
  disposables.push(delay, synth)
  return synth
}

// Lo-fi synth: warm triangle → bitcrusher → lowpass → vibrato → compressor
function makeLofiSynth(): Tone.PolySynth {
  const comp = getMasterCompressor()
  const vibrato = new Tone.Vibrato({ frequency: 2.5, depth: 0.04, wet: 1 }).connect(comp)
  const lp = new Tone.Filter({ frequency: 5500, type: 'lowpass' }).connect(vibrato)
  const crusher = new Tone.BitCrusher({ bits: 10 }).connect(lp)
  const synth = new Tone.PolySynth(Tone.Synth, {
    oscillator: { type: 'triangle' },
    envelope: { attack: 0.04, decay: 0.2, sustain: 0.6, release: 1.2 },
    volume: -4,
  }).connect(crusher)
  disposables.push(vibrato, lp, crusher, synth)
  return synth
}

export function useMidiPlayer() {
  async function toggle(url: string, styleId?: string) {
    if (currentlyPlaying.value === url) {
      cleanup()
      return
    }

    cleanup()
    isLoading.value = true

    try {
      await Tone.start()
      applyVolume(volume.value)

      const isSynth = styleId ? SYNTH_STYLES.has(styleId) : false
      const isPad   = styleId ? PAD_STYLES.has(styleId) : false
      const isLofi  = styleId ? LOFI_STYLES.has(styleId) : false

      // Pre-load all samplers + MIDI in parallel
      const melodicSamplerPromise = getMelodicSampler(styleId)

      const [, buf, drumKit, bassSampler, melodicSampler] = await Promise.all([
        // Piano only needed as fallback for styles without a melodic sampler and no synth
        (!isSynth && !isPad && !isLofi && !melodicSamplerPromise) ? getPianoSampler() : Promise.resolve(null),
        fetch(downloadUrl(url)).then(r => r.arrayBuffer()),
        getDrumKit(styleId),
        getBassSampler(styleId),
        melodicSamplerPromise ?? Promise.resolve(null),
      ])

      const midi = new Midi(buf)

      // Cache parsed notes for the piano roll
      const allNotes: ParsedNote[] = []
      for (const track of midi.tracks) {
        const isPerc = track.instrument.percussion
        for (const n of track.notes) {
          allNotes.push({
            midi: n.midi,
            time: n.time,
            duration: n.duration,
            velocity: n.velocity,
            isPercussion: isPerc,
          })
        }
      }
      midiStore.value[url] = { notes: allNotes, duration: midi.duration }

      Tone.getTransport().bpm.value = midi.header.tempos[0]?.bpm ?? 120

      // Resolve piano fallback if still needed
      const piano = (!isSynth && !isPad && !isLofi && !melodicSampler)
        ? await getPianoSampler()
        : null

      // Create melodic instrument once, shared across chords/melody/arpeggio tracks
      let melodicInstrument: Tone.PolySynth | Tone.Sampler | null = null
      function getMelodicInstrument(): Tone.PolySynth | Tone.Sampler {
        if (melodicInstrument) return melodicInstrument
        if (melodicSampler) {
          melodicInstrument = melodicSampler        // bundled sample (Rhodes, EP2, etc.)
        } else if (isLofi) {
          melodicInstrument = makeLofiSynth()
        } else if (isSynth) {
          melodicInstrument = makeSynthLead()
        } else if (isPad) {
          melodicInstrument = makePad()
        } else {
          melodicInstrument = piano!                // Salamander grand piano
        }
        return melodicInstrument
      }

      for (const track of midi.tracks) {
        if (track.notes.length === 0) continue

        const channel = track.channel ?? 0
        const isPerc = track.instrument.percussion || channel === 9

        if (isPerc) {
          const notes = track.notes.map(n => ({ time: n.time, midi: n.midi, velocity: n.velocity }))
          const part = new Tone.Part<{ time: number; midi: number; velocity: number }>((time, note) => {
            const sampleName = DRUM_PITCH_TO_SAMPLE[note.midi] ?? 'hihat'
            const player = drumKit.player(sampleName)
            player.volume.value = Tone.gainToDb(note.velocity)
            player.start(time)
          }, notes)
          part.start(0)
          scheduledParts.push(part)

        } else if (channel === 1) {
          // Bass — sampled instrument
          const notes = track.notes.map(n => ({
            time: n.time, midi: n.midi, duration: n.duration, velocity: n.velocity,
          }))
          const part = new Tone.Part<{ time: number; midi: number; duration: number; velocity: number }>((time, note) => {
            bassSampler.triggerAttackRelease(
              Tone.Frequency(note.midi, 'midi').toNote(),
              note.duration, time, note.velocity,
            )
          }, notes)
          part.start(0)
          scheduledParts.push(part)

        } else {
          // Chords, melody, arpeggio — style-aware instrument
          const instrument = getMelodicInstrument()
          const notes = track.notes.map(n => ({
            time: n.time, midi: n.midi, duration: n.duration, velocity: n.velocity,
          }))
          const part = new Tone.Part<{ time: number; midi: number; duration: number; velocity: number }>((time, note) => {
            instrument.triggerAttackRelease(
              Tone.Frequency(note.midi, 'midi').toNote(),
              note.duration, time, note.velocity,
            )
          }, notes)
          part.start(0)
          scheduledParts.push(part)
        }
      }

      currentlyPlaying.value = url
      Tone.getTransport().start()

      Tone.getTransport().scheduleOnce(() => {
        cleanup()
      }, midi.duration + 1)
    } catch (e) {
      console.error('MIDI playback error:', e)
      cleanup()
    } finally {
      isLoading.value = false
    }
  }

  function stop() {
    cleanup()
  }

  function getMidiData(url: string): MidiData | null {
    return midiStore.value[url] ?? null
  }

  async function prefetchMidi(url: string): Promise<void> {
    if (midiStore.value[url]) return
    try {
      const buf = await fetch(downloadUrl(url)).then(r => r.arrayBuffer())
      const midi = new Midi(buf)
      const allNotes: ParsedNote[] = []
      for (const track of midi.tracks) {
        const isPerc = track.instrument.percussion
        for (const n of track.notes) {
          allNotes.push({
            midi: n.midi,
            time: n.time,
            duration: n.duration,
            velocity: n.velocity,
            isPercussion: isPerc,
          })
        }
      }
      midiStore.value[url] = { notes: allNotes, duration: midi.duration }
    } catch {
      // silently ignore — piano roll will appear once the user hits play instead
    }
  }

  function setVolume(v: number) {
    volume.value = v
    applyVolume(v)
  }

  return { toggle, stop, currentlyPlaying, isLoading, getMidiData, prefetchMidi, volume, setVolume }
}
