import { ref } from 'vue'
import * as Tone from 'tone'
import { Midi } from '@tonejs/midi'
import { downloadUrl } from '../services/api'

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

// Global so only one track plays at a time
const currentlyPlaying = ref<string | null>(null)
const isLoading = ref(false)

// Cache parsed MIDI data per URL so the piano roll persists after stop
const midiStore = ref<Record<string, MidiData>>({})

let scheduledParts: Tone.Part[] = []
let activeSynths: Tone.ToneAudioNode[] = []

function cleanup() {
  Tone.getTransport().stop()
  Tone.getTransport().cancel()
  scheduledParts.forEach(p => p.dispose())
  activeSynths.forEach(s => s.dispose())
  scheduledParts = []
  activeSynths = []
  currentlyPlaying.value = null
}

function makeMelodicSynth(): Tone.PolySynth {
  return new Tone.PolySynth(Tone.Synth, {
    oscillator: { type: 'triangle' },
    envelope: { attack: 0.02, decay: 0.1, sustain: 0.5, release: 0.8 },
    volume: -6,
  }).toDestination()
}

function makePercSynths() {
  const kick = new Tone.MembraneSynth({ volume: -4 }).toDestination()
  const snare = new Tone.NoiseSynth({
    noise: { type: 'white' },
    envelope: { attack: 0.001, decay: 0.15, sustain: 0, release: 0.05 },
    volume: -10,
  }).toDestination()
  const hat = new Tone.MetalSynth({
    frequency: 400,
    envelope: { attack: 0.001, decay: 0.08, release: 0.01 },
    harmonicity: 5.1,
    modulationIndex: 32,
    resonance: 4000,
    octaves: 1.5,
    volume: -14,
  }).toDestination()
  return { kick, snare, hat }
}

export function useMidiPlayer() {
  async function toggle(url: string) {
    if (currentlyPlaying.value === url) {
      cleanup()
      return
    }

    cleanup()
    isLoading.value = true

    try {
      await Tone.start()
      const res = await fetch(downloadUrl(url))
      const buf = await res.arrayBuffer()
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

      const bpm = midi.header.tempos[0]?.bpm ?? 120
      Tone.getTransport().bpm.value = bpm

      for (const track of midi.tracks) {
        if (track.notes.length === 0) continue

        if (track.instrument.percussion) {
          const { kick, snare, hat } = makePercSynths()
          activeSynths.push(kick, snare, hat)

          const notes = track.notes.map(n => ({ time: n.time, midi: n.midi, velocity: n.velocity }))
          const part = new Tone.Part<{ time: number; midi: number; velocity: number }>((time, note) => {
            if (note.midi === 36 || note.midi === 35) {
              kick.triggerAttackRelease('C1', '8n', time, note.velocity)
            } else if (note.midi === 38 || note.midi === 39 || note.midi === 40) {
              snare.triggerAttackRelease('8n', time, note.velocity)
            } else {
              hat.triggerAttackRelease('16n', time, note.velocity)
            }
          }, notes)
          part.start(0)
          scheduledParts.push(part)
        } else {
          const synth = makeMelodicSynth()
          activeSynths.push(synth)

          const notes = track.notes.map(n => ({
            time: n.time,
            midi: n.midi,
            duration: n.duration,
            velocity: n.velocity,
          }))

          const part = new Tone.Part<{ time: number; midi: number; duration: number; velocity: number }>((time, note) => {
            synth.triggerAttackRelease(
              Tone.Frequency(note.midi, 'midi').toFrequency(),
              note.duration,
              time,
              note.velocity,
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

  return { toggle, stop, currentlyPlaying, isLoading, getMidiData }
}
