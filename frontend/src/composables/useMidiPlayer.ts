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
import { ref } from 'vue'
import * as Tone from 'tone'
import { Midi } from '@tonejs/midi'
import { downloadUrl } from '../services/api'
import { getPianoSampler, getMasterCompressor, getBassBus, getMelodicBus, duckOnKick, resetBusLevels } from '../soundfonts/loader'
import { drumCharacterForStyle } from '../soundfonts/drums'
import { makeSynthKit } from '../soundfonts/synthDrums'
import { getBassSampler } from '../soundfonts/bass'
import { getMelodicSampler, getMelodicSamplerById } from '../soundfonts/melodic'
import { voiceFor } from './useStyleCatalog'
import { encodeWav } from '../utils/wavEncoder'

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

// Styles where ALL parts use synthesis — drum/bass samplers are not loaded
const SYNTH_STYLES = new Set([
  'house', 'techno', 'drum_and_bass', 'synthwave', 'future_bass', 'jersey_club',
  'grime', 'hyperpop',
])
// Styles that load sampled drums/bass but use a synth lead for melodic parts
const MELODIC_SYNTH_STYLES = new Set(['drill', 'dark_trap', 'reggaeton', 'dancehall'])
// Styles that use a slow-attack pad synth for melodic (sampled drums/bass still load)
const PAD_STYLES = new Set([
  'ambient', 'dark_ambient', 'epic_orchestral', 'cinematic',
  'trap_soul', 'cloud_rap',
])
// Lo-fi styles — warm, bit-crushed synth for melodic
const LOFI_STYLES = new Set(['lofi'])

// Global so only one track plays at a time
const currentlyPlaying = ref<string | null>(null)
const nowPlayingLabel = ref<string | null>(null)
const isLoading = ref(false)
const looping = ref(false)
const isRecording = ref(false)
const isRendering = ref(false)
// Per-part mute state, keyed by part name (matches backend _PART_CHANNELS).
export const PLAYER_PARTS = ['drums', 'bass', 'chords', 'melody', 'arpeggio', 'pads', 'counter_melody'] as const
export type PlayerPart = typeof PLAYER_PARTS[number]
const _allUnmuted = (): Record<PlayerPart, boolean> =>
  ({ drums: false, bass: false, chords: false, melody: false, arpeggio: false, pads: false, counter_melody: false })
const channelMuted = ref<Record<PlayerPart, boolean>>(_allUnmuted())

// MIDI channel → part name (see backend _PART_CHANNELS; 9 = GM percussion)
const CHANNEL_PART: Record<number, PlayerPart> = {
  0: 'chords', 1: 'bass', 2: 'melody', 3: 'arpeggio', 4: 'pads', 5: 'counter_melody', 9: 'drums',
}

// Abort token — incremented on every new play; stale toggles bail out after each await
let _playToken = 0
// Duration of the currently loaded track — used by setLooping to apply loopEnd
// live, and by TransportBar / the song timeline for the time readout.
const durationSeconds = ref(0)

// Playback position, polled at ~7 Hz while the transport runs (cheap enough
// for a playhead + time display without a per-frame loop).
const positionSeconds = ref(0)
const isPaused = ref(false)
let _positionTimer: ReturnType<typeof setInterval> | null = null

function startPositionPolling() {
  stopPositionPolling()
  positionSeconds.value = 0
  _positionTimer = setInterval(() => {
    positionSeconds.value = Tone.getTransport().seconds
  }, 150)
}

function stopPositionPolling() {
  if (_positionTimer !== null) {
    clearInterval(_positionTimer)
    _positionTimer = null
  }
  positionSeconds.value = 0
}

// Master volume: 0–100 maps to dB via gainToDb, persisted across sessions
const _savedVolume = typeof localStorage !== 'undefined'
  ? Number(localStorage.getItem('genregrid_volume') ?? 80)
  : 80
const volume = ref(isNaN(_savedVolume) ? 80 : _savedVolume)

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
  isPaused.value = false
  Tone.getTransport().stop()
  Tone.getTransport().cancel()
  Tone.getTransport().loop = false
  resetBusLevels()   // never leave a sidechain duck applied after stop
  scheduledParts.forEach(p => p.dispose())
  disposables.forEach(d => d.dispose())
  scheduledParts = []
  disposables = []
  durationSeconds.value = 0
  stopPositionPolling()
  currentlyPlaying.value = null
  nowPlayingLabel.value = null
}

// Melody lead — a dedicated, in-tune, articulate voice for the melodic LINE.
// Replaces two bad melody voices: the harsh heavily-chorused sawtooth (which
// wavered out of tune) and the pad (0.8 s attack, so fast melody notes never
// spoke). Fast attack so every note reads, a tamed low-pass so it's not harsh,
// and only a whisper of chorus so it stays in tune. `soft` warms it and adds
// space for ambient/cinematic styles.
function makeMelodyLead(soft: boolean, output: Tone.ToneAudioNode = getMelodicBus()): Tone.PolySynth {
  // Chorus + delay now live once on the shared melodic bus (see getMelodicBus).
  const filter = new Tone.Filter({ frequency: soft ? 3000 : 3800, type: 'lowpass', rolloff: -12, Q: 0.8 }).connect(output)
  const synth = new Tone.PolySynth(Tone.Synth, {
    oscillator: soft ? { type: 'triangle' } : { type: 'sawtooth' },
    envelope: soft
      ? { attack: 0.03, decay: 0.2,  sustain: 0.75, release: 0.8 }
      : { attack: 0.008, decay: 0.15, sustain: 0.65, release: 0.3 },
    volume: soft ? -9 : -10,
  }).connect(filter)
  disposables.push(filter, synth)
  return synth
}

// Synth comp: detuned/warm saw stack, slower attack, rolled-off highs.
// Deliberately darker than makeSynthLead so CHORDS don't collide with the melody
// timbre on electronic styles (previously both used the same sawtooth lead).
function makeSynthChords(output: Tone.ToneAudioNode = getMelodicBus()): Tone.PolySynth {
  const lp = new Tone.Filter({ frequency: 2600, type: 'lowpass', rolloff: -12 }).connect(output)
  const synth = new Tone.PolySynth(Tone.Synth, {
    oscillator: { type: 'fatsawtooth', count: 3, spread: 22 },
    envelope: { attack: 0.06, decay: 0.25, sustain: 0.65, release: 0.6 },
    volume: -15,
  }).connect(lp)
  disposables.push(lp, synth)
  return synth
}

// Arp pluck: short, bright, decaying voice with a synced delay tail. Gives the
// arpeggio part its own identity instead of doubling the chord/lead timbre.
function makeArpPluck(output: Tone.ToneAudioNode = getMelodicBus()): Tone.PolySynth {
  const lp = new Tone.Filter({ frequency: 4200, type: 'lowpass', rolloff: -12 }).connect(output)
  const synth = new Tone.PolySynth(Tone.Synth, {
    oscillator: { type: 'triangle' },
    envelope: { attack: 0.004, decay: 0.18, sustain: 0.0, release: 0.25 },
    volume: -12,
  }).connect(lp)
  disposables.push(lp, synth)
  return synth
}

// Pad: slow-attack triangle + long feedback delay (ambient, cinematic, etc.)
function makePad(output: Tone.ToneAudioNode = getMelodicBus()): Tone.PolySynth {
  const synth = new Tone.PolySynth(Tone.Synth, {
    oscillator: { type: 'triangle' },
    envelope: { attack: 0.8, decay: 0.3, sustain: 0.7, release: 2.0 },
    volume: -10,
  }).connect(output)
  disposables.push(synth)
  return synth
}

// Strings ensemble: soft detuned-saw stack for the counter-melody part —
// articulate enough to read as a line, slow and dark enough to sit behind
// the lead instead of competing with it.
function makeStrings(output: Tone.ToneAudioNode = getMelodicBus()): Tone.PolySynth {
  const lp = new Tone.Filter({ frequency: 2400, type: 'lowpass', rolloff: -12 }).connect(output)
  const synth = new Tone.PolySynth(Tone.Synth, {
    oscillator: { type: 'fatsawtooth', count: 3, spread: 14 },
    envelope: { attack: 0.12, decay: 0.3, sustain: 0.8, release: 1.2 },
    volume: -14,
  }).connect(lp)
  disposables.push(lp, synth)
  return synth
}

// Synth bass: sawtooth MonoSynth with portamento — house/techno/dnb etc.
function makeSynthBass(): Tone.MonoSynth {
  const comp = getBassBus()
  const bass = new Tone.MonoSynth({
    oscillator: { type: 'sawtooth' },
    filter: { Q: 2.5, type: 'lowpass', rolloff: -24 },
    envelope: { attack: 0.01, decay: 0.08, sustain: 0.9, release: 0.3 },
    filterEnvelope: { attack: 0.04, decay: 0.2, sustain: 0.5, release: 0.3, baseFrequency: 180, octaves: 2.6 },
    portamento: 0.035,
    volume: -3,
  }).connect(comp)
  disposables.push(bass)
  return bass
}

// Lo-fi synth: warm triangle → bitcrusher → lowpass → vibrato → compressor
function makeLofiSynth(output: Tone.ToneAudioNode = getMelodicBus()): Tone.PolySynth {
  const vibrato = new Tone.Vibrato({ frequency: 2.5, depth: 0.04, wet: 1 }).connect(output)
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

// Tone.Offline() always renders "asynchronously": internally it steps through
// the render in 128-sample blocks and, once per second of rendered audio,
// awaits a 1ms setTimeout so the main thread isn't blocked for the whole
// render. An earlier version of this function skipped those yields entirely
// (render(false)) for maximum speed — but with no note actually routed
// through Tone's Transport any more (see the trigger-ordering comment in
// offlineRender below), each of those per-tick steps got dramatically
// cheaper, so the yields cost much less relative to the work they used to
// interrupt. Keeping them (render(true)) means the tab stays responsive
// during a render — you can keep working, start another export, or play a
// preview — for a render time difference that's now marginal.
//
// This also used to swap Tone's ambient context globally for the whole
// render via Tone.setContext(), which corrupted any other Tone.js activity
// (playback, another render) that started before the swap was undone —
// exactly the kind of concurrent use the yields above are meant to allow.
// Building the OfflineContext and handing it directly to the caller instead
// avoids that: every node the caller creates must be given { context }
// explicitly so it lives in the offline graph rather than the ambient one.
async function renderOfflineFast(
  callback: (context: Tone.OfflineContext) => Promise<void> | void,
  duration: number,
  channels = 2,
): Promise<Tone.ToneAudioBuffer> {
  const context = new Tone.OfflineContext(channels, duration, Tone.getContext().sampleRate)
  await callback(context)
  return await context.render(true)
}

export function useMidiPlayer() {
  async function toggle(url: string, styleId?: string, label?: string) {
    if (currentlyPlaying.value === url) {
      cleanup()
      return
    }

    cleanup()
    const token = ++_playToken
    isLoading.value = true
    nowPlayingLabel.value = label ?? url.split('/').pop() ?? url

    try {
      await Tone.start()
      if (token !== _playToken) return
      console.log(`[play] Tone.start OK — ctx=${Tone.getContext().state} rate=${Tone.getContext().rawContext.sampleRate} style=${styleId ?? 'none'}`)

      applyVolume(volume.value)
      console.log(`[play] volume applied: destVol=${Tone.getDestination().volume.value.toFixed(1)}dB`)

      const isSynth        = styleId ? SYNTH_STYLES.has(styleId) : false
      const isMelodicSynth = styleId ? MELODIC_SYNTH_STYLES.has(styleId) : false
      const isPad          = styleId ? PAD_STYLES.has(styleId) : false
      const isLofi         = styleId ? LOFI_STYLES.has(styleId) : false

      // Pre-load all samplers + MIDI in parallel.
      // SYNTH_STYLES use synthesis for drums + bass — skip those sampler loads entirely.
      const melodicSamplerPromise = getMelodicSampler(styleId)

      // Instrument-identity voices (Phase 3): each part may name a sampled
      // playback voice ("electric_piano_1") via the style's instrumentation —
      // preload those per part; non-sampled voices ("melody_lead") map to
      // synth families below, and null falls back to legacy style logic.
      const _partVoice = {
        chords: voiceFor(styleId, 'chords'),
        melody: voiceFor(styleId, 'melody'),
        arpeggio: voiceFor(styleId, 'arpeggio'),
      }
      const _samplerP = (v: string | null) =>
        (v ? getMelodicSamplerById(v) : null) ?? Promise.resolve(null)

      const fetchUrl = url.startsWith('blob:') || url.startsWith('data:') ? url : downloadUrl(url)
      const [, buf, bassSampler, melodicSampler, chordsSamp, melodySamp, arpSamp] = await Promise.all([
        (!isSynth && !isPad && !isLofi && !isMelodicSynth && !melodicSamplerPromise) ? getPianoSampler() : Promise.resolve(null),
        fetch(fetchUrl).then(r => r.arrayBuffer()),
        isSynth ? Promise.resolve(null) : getBassSampler(styleId),
        melodicSamplerPromise ?? Promise.resolve(null),
        _samplerP(_partVoice.chords),
        _samplerP(_partVoice.melody),
        _samplerP(_partVoice.arpeggio),
      ])

      if (token !== _playToken) return

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
      const piano = (!isSynth && !isPad && !isLofi && !isMelodicSynth && !melodicSampler)
        ? await getPianoSampler()
        : null

      // Synthesized drum kit — one voice per articulation, tuned to the style's
      // character. Replaces the old thin/fake-cymbal samples for every genre.
      const drumKit = makeSynthKit(drumCharacterForStyle(styleId))
      disposables.push(...drumKit.nodes)
      let _synthBass: Tone.MonoSynth | null = null
      const getSynthBass = () => { if (!_synthBass) _synthBass = makeSynthBass(); return _synthBass }

      // Read the static pan (CC10) a track was written with and return the -1..1
      // value a Tone.Panner expects. @tonejs/midi normalises CC values to 0..1.
      function trackPan(track: typeof midi.tracks[number]): number {
        const cc = track.controlChanges?.[10]
        if (cc && cc.length) return Math.max(-1, Math.min(1, cc[cc.length - 1].value * 2 - 1))
        return 0
      }

      // Melodic voices are resolved per part (chords / melody / arpeggio) so they
      // no longer share one timbre. Each synth-based voice is routed through its
      // own Panner fed from the part's CC10 so the server-side stereo placement is
      // actually audible. Bundled samplers (Rhodes, vibraphone, etc.) and the piano
      // fallback are cached/shared with their own fx chains, so chords+melody reuse
      // that one instrument (acoustic styles read fine sharing a voice); only the
      // arpeggio gets a distinct pluck on top.
      const voiceCache: Record<number, Tone.PolySynth | Tone.Sampler> = {}

      function makePanned(build: (out: Tone.ToneAudioNode) => Tone.PolySynth, pan: number): Tone.PolySynth {
        const panner = new Tone.Panner(pan).connect(getMelodicBus())
        disposables.push(panner)
        return build(panner)
      }

      // channel 0 = chords, 2 = melody, 3 = arpeggio, 4 = pads,
      // 5 = counter-melody (see backend _PART_CHANNELS)
      function getMelodicInstrument(channel: number, pan: number): Tone.PolySynth | Tone.Sampler {
        if (voiceCache[channel]) return voiceCache[channel]

        // Instrument-identity resolution first: a sampled voice loaded for
        // this part wins; a wind/brass "melody_lead" voice gets the articulate
        // soft lead (matches the breath-phrased writing). Anything unresolved
        // falls through to the legacy style-family logic below.
        const _voiceSamplers: Record<number, Tone.Sampler | null> = { 0: chordsSamp, 2: melodySamp, 3: arpSamp }
        const _voiceIds: Record<number, string | null> = { 0: _partVoice.chords, 2: _partVoice.melody, 3: _partVoice.arpeggio }
        if (_voiceSamplers[channel]) {
          voiceCache[channel] = _voiceSamplers[channel]!
          return voiceCache[channel]
        }
        if (channel === 2 && _voiceIds[2] === 'melody_lead') {
          voiceCache[2] = makePanned((out) => makeMelodyLead(true, out), pan)
          return voiceCache[2]
        }

        let inst: Tone.PolySynth | Tone.Sampler
        if (channel === 4) {
          // Pads part — always the sustained pad voice, never the sampler, so
          // the layer washes behind the comp regardless of style.
          inst = makePanned(makePad, pan)
        } else if (channel === 5) {
          // Counter-melody — soft string ensemble under the lead.
          inst = makePanned(makeStrings, pan)
        } else if (channel === 3) {
          // Arpeggio — always its own voice so it sparkles above the comp.
          inst = melodicSampler ?? makePanned(makeArpPluck, pan)
        } else if (melodicSampler) {
          inst = melodicSampler                       // bundled sample (Rhodes, EP2, vibes…)
        } else if (isLofi) {
          inst = makePanned(makeLofiSynth, pan)
        } else if (isSynth || isMelodicSynth) {
          // Chords get the warm comp stack; melody gets the dedicated lead.
          inst = channel === 0
            ? makePanned(makeSynthChords, pan)
            : makePanned((out) => makeMelodyLead(false, out), pan)
        } else if (isPad) {
          // Chords hold the slow pad; the melody needs a fast-attack lead so its
          // notes actually articulate instead of smearing under the pad envelope.
          inst = channel === 0
            ? makePanned(makePad, pan)
            : makePanned((out) => makeMelodyLead(true, out), pan)
        } else {
          inst = piano!                               // Salamander grand piano (shared)
        }
        voiceCache[channel] = inst
        return inst
      }

      for (const track of midi.tracks) {
        if (track.notes.length === 0) continue

        const channel = track.channel ?? 0
        const isPerc = track.instrument.percussion || channel === 9

        if (isPerc) {
          // Electronic styles get a sidechain pump: each kick briefly ducks the
          // melodic and bass buses so the mix breathes around the four-on-the-floor.
          const pump = isSynth
          const notes = track.notes.map(n => ({ time: n.time, midi: n.midi, velocity: n.velocity }))
          const part = new Tone.Part<{ time: number; midi: number; velocity: number }>((time, note) => {
            if (channelMuted.value.drums) return
            drumKit.trigger(note.midi, note.velocity, time)
            if (pump && note.midi === 36) duckOnKick(time)
          }, notes)
          part.start(0)
          scheduledParts.push(part)

        } else if (channel === 1) {
          // Bass — synthesis for electronic styles, sampler otherwise
          const bassInst = isSynth ? getSynthBass() : bassSampler!
          const notes = track.notes.map(n => ({
            time: n.time, midi: n.midi, duration: n.duration, velocity: n.velocity,
          }))
          const part = new Tone.Part<{ time: number; midi: number; duration: number; velocity: number }>((time, note) => {
            if (channelMuted.value.bass) return
            bassInst.triggerAttackRelease(
              Tone.Frequency(note.midi, 'midi').toNote(),
              note.duration, time, note.velocity,
            )
          }, notes)
          part.start(0)
          scheduledParts.push(part)

        } else {
          // Chords, melody, arpeggio — distinct style-aware voice per part, each
          // placed in the stereo field from its CC10 pan.
          const instrument = getMelodicInstrument(channel, trackPan(track))
          const notes = track.notes.map(n => ({
            time: n.time, midi: n.midi, duration: n.duration, velocity: n.velocity,
          }))
          const mutePart = CHANNEL_PART[channel] ?? 'chords'
          const part = new Tone.Part<{ time: number; midi: number; duration: number; velocity: number }>((time, note) => {
            if (channelMuted.value[mutePart]) return
            instrument.triggerAttackRelease(
              Tone.Frequency(note.midi, 'midi').toNote(),
              note.duration, time, note.velocity,
            )
          }, notes)
          part.start(0)
          scheduledParts.push(part)
        }
      }

      console.log(`[play] built graph — tracks=${midi.tracks.length} parts=${scheduledParts.length} disposables=${disposables.length} duration=${midi.duration.toFixed(2)}s bpm=${Tone.getTransport().bpm.value}`)

      durationSeconds.value = midi.duration
      currentlyPlaying.value = url

      if (looping.value) {
        Tone.getTransport().loop = true
        Tone.getTransport().loopStart = 0
        Tone.getTransport().loopEnd = midi.duration
      } else {
        Tone.getTransport().loop = false
      }

      Tone.getTransport().start()
      console.log(`[play] transport started — state=${Tone.getTransport().state} seconds=${Tone.getTransport().seconds.toFixed(2)} loop=${looping.value}`)
      startPositionPolling()

      if (!looping.value) {
        Tone.getTransport().scheduleOnce(() => { cleanup() }, midi.duration + 1)
      }
    } catch (e) {
      console.error('MIDI playback error:', e)
      cleanup()
    } finally {
      // Only clear loading state if this toggle is still the active one.
      // A stale (token-mismatched) toggle must NOT clear isLoading — the
      // newer toggle is still loading and needs isLoading to stay true so
      // that play buttons remain disabled until the new track is ready.
      if (token === _playToken) isLoading.value = false
    }
  }

  function setLooping(v: boolean) {
    looping.value = v
    if (v && durationSeconds.value > 0) {
      Tone.getTransport().loopStart = 0
      Tone.getTransport().loopEnd = durationSeconds.value
    }
    Tone.getTransport().loop = v
  }

  async function exportAudio(
    url: string,
    styleId: string | undefined,
    durationSeconds: number,
    label: string,
    onProgress?: (v: number) => void,
  ): Promise<Blob> {
    isRecording.value = true
    try {
      const wasLooping = looping.value
      looping.value = false
      await toggle(url, styleId, label)
      looping.value = wasLooping

      const comp = getMasterCompressor()
      const recorder = new Tone.Recorder()
      comp.connect(recorder)
      recorder.start()

      const totalMs = (durationSeconds + 1.5) * 1000
      await new Promise<void>(resolve => {
        const start = Date.now()
        const iv = setInterval(() => {
          const elapsed = Date.now() - start
          onProgress?.(Math.min(elapsed / totalMs, 0.99))
          if (elapsed >= totalMs) { clearInterval(iv); resolve() }
        }, 200)
      })

      const blob = await recorder.stop()
      comp.disconnect(recorder)
      recorder.dispose()
      onProgress?.(1)
      cleanup()
      return blob
    } finally {
      isRecording.value = false
    }
  }

  /**
   * Render to WAV using Tone.Offline (faster than real-time).
   * Uses a fresh synth-only signal path — no cached samplers needed.
   * channelFilter controls which instrument group to include (for stems).
   */
  async function offlineRender(
    url: string,
    styleId: string | undefined,
    durationSeconds: number,
    channelFilter: 'all' | 'melodic' | PlayerPart = 'all',
    onProgress?: (v: number) => void,
  ): Promise<Blob> {
    isRendering.value = true
    onProgress?.(0.02)
    try {
      const fetchUrl = url.startsWith('blob:') || url.startsWith('data:') ? url : downloadUrl(url)
      const buf = await fetch(fetchUrl).then(r => r.arrayBuffer())
      const midi = new Midi(buf)
      const bpm = midi.header.tempos[0]?.bpm ?? 120

      const isPad  = styleId ? PAD_STYLES.has(styleId)  : false
      const isLofi = styleId ? LOFI_STYLES.has(styleId) : false
      const isSynth = styleId ? SYNTH_STYLES.has(styleId) : false

      onProgress?.(0.08)

      const tail = isPad ? 2.5 : 1.2
      const totalDuration = durationSeconds + tail
      if (!Number.isFinite(totalDuration) || totalDuration <= 0) {
        throw new Error('Invalid render duration — the source MIDI may be empty or malformed')
      }

      // Which parts this render includes: 'all', the legacy 'melodic' bucket,
      // or any single part name (per-part stem export).
      const wantsPart = (p: PlayerPart): boolean =>
        channelFilter === 'all' || channelFilter === p ||
        (channelFilter === 'melodic' && p !== 'drums' && p !== 'bass')

      // The Web Audio API gives no incremental progress for an OfflineAudioContext
      // render, so a long song (several minutes of audio, synthesized+effected)
      // would otherwise sit at a frozen percentage for its entire render time and
      // look hung even when it's working. Nudge the bar forward on a timer, and
      // give up with a clear error instead of hanging the UI forever if the
      // render graph genuinely stalls (should not happen, but silent infinite
      // waits are worse than a surfaced error).
      let simulated = 0.08
      const progressTimer = setInterval(() => {
        simulated = Math.min(0.89, simulated + 0.01)
        onProgress?.(simulated)
      }, 400)
      const timeoutMs = Math.max(45_000, totalDuration * 4000)
      let timeoutHandle: ReturnType<typeof setTimeout> | null = null
      const timeout = new Promise<never>((_, reject) => {
        timeoutHandle = setTimeout(
          () => reject(new Error('WAV render timed out — try again, or export a shorter section')),
          timeoutMs,
        )
      })

      const renderPromise = renderOfflineFast(async (context) => {
        const dest = context.destination
        dest.volume.value = 0
        // Plain gain, not a Tone.Compressor — a DynamicsCompressorNode renders silence on
        // Linux packaged Electron (see getMasterCompressor in loader.ts), which would make
        // WAV exports silent there too.
        const comp = new Tone.Gain({ context, gain: 1 }).connect(dest)

        // Only needed so Transport-relative delay-time notation ('8n', '4n', …)
        // in the effects below resolves against the song's real tempo — no note
        // is actually scheduled through the Transport (see below). This is the
        // offline context's OWN transport, not the ambient one used by live
        // playback — mutating that would have audibly retempo'd anything
        // playing concurrently while this export ran.
        context.transport.bpm.value = bpm

        // ── Drum kit ─────────────────────────────────────────────────────
        // Same synthesized engine as live playback, routed to the offline
        // compressor so the export matches what the user auditions.
        const drumKit = wantsPart('drums')
          ? makeSynthKit(drumCharacterForStyle(styleId), comp, context)
          : null

        // ── Bass synth ───────────────────────────────────────────────────
        let bassSynth: Tone.MonoSynth | null = null
        if (wantsPart('bass')) {
          bassSynth = new Tone.MonoSynth({
            context,
            oscillator: { type: 'sawtooth' },
            filter: { Q: 2, type: 'lowpass', rolloff: -24 },
            envelope: { attack: 0.01, decay: 0.1, sustain: 0.9, release: 0.5 },
            filterEnvelope: { attack: 0.06, decay: 0.2, sustain: 0.5, release: 0.5, baseFrequency: 200, octaves: 2.6 },
            volume: -3,
          }).connect(comp)
        }

        // ── Melodic synths ───────────────────────────────────────────────
        // Mirror live playback: chords / melody / arpeggio each get a distinct
        // voice, panned from the part's CC10 so the export matches the preview.
        const panForChannel = (ch: number): number => {
          const track = midi.tracks.find(t => (t.channel ?? 0) === ch)
          const cc = track?.controlChanges?.[10]
          if (cc && cc.length) return Math.max(-1, Math.min(1, cc[cc.length - 1].value * 2 - 1))
          return 0
        }
        const mkVoice = (variant: 'chords' | 'lead' | 'arp' | 'pads' | 'strings', pan: number): Tone.PolySynth => {
          const panner = new Tone.Panner({ context, pan }).connect(comp)
          if (variant === 'arp') {
            const delay = new Tone.FeedbackDelay({ context, delayTime: '8n.', feedback: 0.24, wet: 0.16 }).connect(panner)
            const lp = new Tone.Filter({ context, frequency: 4200, type: 'lowpass' }).connect(delay)
            return new Tone.PolySynth({
              context,
              voice: Tone.Synth,
              options: {
                oscillator: { type: 'triangle' },
                envelope: { attack: 0.004, decay: 0.18, sustain: 0.0, release: 0.25 },
                volume: -11,
              },
            }).connect(lp)
          }
          if (variant === 'pads') {
            // Pads part — same sustained wash as live playback's makePad
            const delay = new Tone.FeedbackDelay({ context, delayTime: '4n', feedback: 0.4, wet: 0.3 }).connect(panner)
            return new Tone.PolySynth({
              context,
              voice: Tone.Synth,
              options: {
                oscillator: { type: 'triangle' },
                envelope: { attack: 0.8, decay: 0.3, sustain: 0.7, release: 2.0 },
                volume: -10,
              },
            }).connect(delay)
          }
          if (variant === 'strings') {
            // Counter-melody — matches makeStrings in live playback
            const lp = new Tone.Filter({ context, frequency: 2400, type: 'lowpass' }).connect(panner)
            const chorus = new Tone.Chorus({ context, frequency: 0.8, depth: 0.35, wet: 0.3 }).connect(lp)
            chorus.start()
            return new Tone.PolySynth({
              context,
              voice: Tone.Synth,
              options: {
                oscillator: { type: 'fatsawtooth', count: 3, spread: 14 },
                envelope: { attack: 0.12, decay: 0.3, sustain: 0.8, release: 1.2 },
                volume: -14,
              },
            }).connect(chorus)
          }
          // Winds/brass ("melody_lead" voices) get the articulate lead in the
          // offline render too — the writing is breath-phrased and monophonic,
          // and the generic triangle poly smears it.
          const _isWindLead = voiceFor(styleId, 'melody') === 'melody_lead'
          if (variant === 'lead' && (isPad || isSynth || _isWindLead)) {
            // Dedicated articulate melody lead (matches makeMelodyLead in live play):
            // fast attack, tamed low-pass, only a whisper of chorus so it stays in tune.
            const soft = isPad
            const delay = new Tone.FeedbackDelay({ context, delayTime: '8n.', feedback: 0.22, wet: soft ? 0.22 : 0.14 }).connect(panner)
            const chorus = new Tone.Chorus({ context, frequency: 1.8, depth: 0.12, wet: 0.14 }).connect(delay)
            chorus.start()
            const lp = new Tone.Filter({ context, frequency: soft ? 3000 : 3800, type: 'lowpass', rolloff: -12, Q: 0.8 }).connect(chorus)
            return new Tone.PolySynth({
              context,
              voice: Tone.Synth,
              options: {
                oscillator: soft ? { type: 'triangle' } : { type: 'sawtooth' },
                envelope: soft
                  ? { attack: 0.03, decay: 0.2,  sustain: 0.75, release: 0.8 }
                  : { attack: 0.008, decay: 0.15, sustain: 0.65, release: 0.3 },
                volume: soft ? -9 : -10,
              },
            }).connect(lp)
          }
          if (isPad) {
            const delay = new Tone.FeedbackDelay({ context, delayTime: '4n', feedback: 0.38, wet: 0.28 }).connect(panner)
            return new Tone.PolySynth({
              context,
              voice: Tone.Synth,
              options: {
                oscillator: { type: 'triangle' },
                envelope: { attack: 0.8, decay: 0.3, sustain: 0.7, release: 2.0 },
                volume: -7,
              },
            }).connect(delay)
          }
          if (isLofi) {
            const lp = new Tone.Filter({ context, frequency: 5200, type: 'lowpass' }).connect(panner)
            return new Tone.PolySynth({
              context,
              voice: Tone.Synth,
              options: {
                oscillator: { type: 'triangle' },
                envelope: { attack: 0.04, decay: 0.2, sustain: 0.6, release: 1.2 },
                volume: -4,
              },
            }).connect(lp)
          }
          if (isSynth) {
            if (variant === 'chords') {
              const lp = new Tone.Filter({ context, frequency: 2600, type: 'lowpass' }).connect(panner)
              const chorus = new Tone.Chorus({ context, frequency: 1.4, depth: 0.5, wet: 0.35 }).connect(lp)
              chorus.start()
              return new Tone.PolySynth({
                context,
                voice: Tone.Synth,
                options: {
                  oscillator: { type: 'fatsawtooth', count: 3, spread: 22 },
                  envelope: { attack: 0.06, decay: 0.25, sustain: 0.65, release: 0.6 },
                  volume: -12,
                },
              }).connect(chorus)
            }
            const delay = new Tone.PingPongDelay({ context, delayTime: '8n', feedback: 0.18, wet: 0.1 }).connect(panner)
            const chorus = new Tone.Chorus({ context, frequency: 3, depth: 0.4, wet: 0.22 }).connect(delay)
            chorus.start()
            return new Tone.PolySynth({
              context,
              voice: Tone.Synth,
              options: {
                oscillator: { type: 'sawtooth' },
                envelope: { attack: 0.01, decay: 0.12, sustain: 0.8, release: 0.4 },
                volume: -9,
              },
            }).connect(chorus)
          }
          return new Tone.PolySynth({
            context,
            voice: Tone.Synth,
            options: {
              oscillator: { type: 'triangle' },
              envelope: { attack: 0.02, decay: 0.15, sustain: 0.7, release: 0.9 },
              volume: -8,
            },
          }).connect(panner)
        }

        let chordsSynth: Tone.PolySynth | null = null
        let leadSynth: Tone.PolySynth | null = null
        let arpSynth: Tone.PolySynth | null = null
        let padsSynth: Tone.PolySynth | null = null
        let stringsSynth: Tone.PolySynth | null = null
        const hasTrackOn = (ch: number) =>
          midi.tracks.some(t => (t.channel ?? 0) === ch && t.notes.length > 0)
        // Only built when wanted AND the file actually carries the part — keeps
        // the offline graph light for single-stem renders.
        if (wantsPart('chords'))   chordsSynth = mkVoice('chords', panForChannel(0))
        if (wantsPart('melody'))   leadSynth   = mkVoice('lead',   panForChannel(2))
        if (wantsPart('arpeggio')) arpSynth    = mkVoice('arp',    panForChannel(3))
        if (wantsPart('pads') && hasTrackOn(4))           padsSynth    = mkVoice('pads',    panForChannel(4))
        if (wantsPart('counter_melody') && hasTrackOn(5)) stringsSynth = mkVoice('strings', panForChannel(5))

        // ── Schedule MIDI events ─────────────────────────────────────────
        // Triggered directly at each note's absolute time (seconds from render
        // start — exactly what the parsed MIDI already gives us) instead of via
        // Tone.getTransport().schedule(). The Transport's tick-driven scheduler
        // is designed for live, tempo-relative playback; routing every note
        // through it here forced the offline render to walk its full timeline
        // for each of the render's ~128-sample ticks, which is the dominant
        // cost for a multi-minute song. Triggering the synths directly uses
        // native Web Audio parameter scheduling instead, which the offline
        // render can bounce in one pass — this is also the pattern Tone.js's
        // own docs use for offline rendering.
        //
        // Tone.js requires each voice's start times to arrive STRICTLY
        // increasing (the Transport used to guarantee that for us by firing
        // scheduled callbacks in time order regardless of scheduling order).
        // Triggering directly means the JS *call* order is what Tone.js sees,
        // and this loop processes one track fully before the next — so two
        // tracks sharing a voice (e.g. the single bassSynth instance) could
        // call it out of time order. Sorting fixes ordering but NOT exact ties
        // (two notes computed to the same float time — plausible for drum
        // rolls/simultaneous hits) since Tone.js rejects equal times too, so
        // after sorting each fire time is nudged forward by a sub-millisecond
        // epsilon whenever it would collide with (or trail) the previous one —
        // inaudible, but guarantees strict monotonicity for every voice.
        const triggers: { time: number; fn: (time: number) => void }[] = []
        for (const track of midi.tracks) {
          if (track.notes.length === 0) continue
          const channel = track.channel ?? 0
          const isPerc = track.instrument.percussion || channel === 9

          if (isPerc && drumKit) {
            for (const n of track.notes) {
              triggers.push({ time: n.time, fn: (time) => drumKit.trigger(n.midi, n.velocity, time) })
            }
          } else if (channel === 1 && bassSynth) {
            const bass = bassSynth
            for (const n of track.notes) {
              const note = Tone.Frequency(n.midi, 'midi').toNote()
              triggers.push({ time: n.time, fn: (time) => bass.triggerAttackRelease(note, n.duration, time, n.velocity) })
            }
          } else if (!isPerc && channel !== 1) {
            // channel 2 = melody (lead), 3 = arpeggio (pluck), 4 = pads,
            // 5 = counter-melody (strings), else chords. A null synth means the
            // part isn't included in this render (per-part stem filtering).
            const synth = channel === 3 ? arpSynth
              : channel === 2 ? leadSynth
              : channel === 4 ? padsSynth
              : channel === 5 ? stringsSynth
              : chordsSynth
            if (synth) {
              for (const n of track.notes) {
                const note = Tone.Frequency(n.midi, 'midi').toNote()
                triggers.push({ time: n.time, fn: (time) => synth.triggerAttackRelease(note, n.duration, time, n.velocity) })
              }
            }
          }
        }
        triggers.sort((a, b) => a.time - b.time)
        const EPSILON = 0.0005   // 0.5 ms — well below audible/perceptible timing resolution
        let lastTime = -Infinity
        for (const t of triggers) {
          const time = t.time > lastTime ? t.time : lastTime + EPSILON
          lastTime = time
          t.fn(time)
        }
      }, totalDuration, 2)

      // If the timeout wins the race, the render keeps running in the background
      // (an OfflineAudioContext can't be cancelled) — swallow its eventual
      // settlement so a late rejection doesn't surface as an unhandled promise.
      renderPromise.catch(() => {})

      let toneBuffer: Awaited<typeof renderPromise>
      try {
        toneBuffer = await Promise.race([renderPromise, timeout])
      } finally {
        clearInterval(progressTimer)
        if (timeoutHandle !== null) clearTimeout(timeoutHandle)
      }

      onProgress?.(0.92)
      const ab = toneBuffer.get()
      if (!ab) throw new Error('Offline render returned empty buffer')
      const blob = encodeWav(ab)
      onProgress?.(1)
      return blob
    } finally {
      isRendering.value = false
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
      const fetchUrl = url.startsWith('blob:') || url.startsWith('data:') ? url : downloadUrl(url)
      const buf = await fetch(fetchUrl).then(r => r.arrayBuffer())
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

  function toggleMute(ch: PlayerPart) {
    channelMuted.value = { ...channelMuted.value, [ch]: !channelMuted.value[ch] }
  }

  function soloPart(ch: PlayerPart) {
    // Solo = mute everything else. Soloing an already-soloed part unmutes all.
    const isSolo = !channelMuted.value[ch] && PLAYER_PARTS.every(p => p === ch || channelMuted.value[p])
    if (isSolo) {
      channelMuted.value = _allUnmuted()
    } else {
      const next = _allUnmuted()
      for (const p of PLAYER_PARTS) next[p] = p !== ch
      channelMuted.value = next
    }
  }

  function seek(seconds: number) {
    // Jump the transport while a track is playing (timeline section clicks).
    if (currentlyPlaying.value === null) return
    Tone.getTransport().seconds = Math.max(0, seconds)
    positionSeconds.value = Math.max(0, seconds)   // snap the playhead immediately
  }

  function togglePause() {
    // Pause/resume the transport in place (scheduled parts pick up where they left off)
    if (currentlyPlaying.value === null) return
    if (isPaused.value) {
      Tone.getTransport().start()
      isPaused.value = false
    } else {
      Tone.getTransport().pause()
      isPaused.value = true
    }
  }

  function isPlayingUrl(url: string): boolean {
    return currentlyPlaying.value === url
  }

  function setVolume(v: number) {
    volume.value = v
    applyVolume(v)
    try { localStorage.setItem('genregrid_volume', String(v)) } catch { /* storage unavailable */ }
  }

  // Warm up samplers in the background as soon as a generation result arrives,
  // so the first play button click has no loading delay.
  function prefetchSamplers(styleId?: string) {
    const isSynth = styleId ? SYNTH_STYLES.has(styleId) : false
    const isPad   = styleId ? PAD_STYLES.has(styleId)   : false
    const isLofi  = styleId ? LOFI_STYLES.has(styleId)  : false
    // Synth/pad/lofi styles use in-memory oscillators — nothing to fetch.
    // Drums are synthesized for every style now, so only bass/melodic samplers load.
    if (isSynth || isPad || isLofi) return
    Promise.all([
      getBassSampler(styleId),
      getMelodicSampler(styleId),
    ]).catch(() => { /* best-effort, ignore network errors */ })
  }

  return { toggle, stop, currentlyPlaying, nowPlayingLabel, isLoading, getMidiData, prefetchMidi, prefetchSamplers, volume, setVolume, looping, setLooping, isRecording, exportAudio, offlineRender, isRendering, channelMuted, toggleMute, soloPart, seek, positionSeconds, durationSeconds, isPlayingUrl, isPaused, togglePause }
}
