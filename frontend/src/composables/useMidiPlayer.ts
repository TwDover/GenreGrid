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
import { ref, computed } from 'vue'
import * as Tone from 'tone'
import { Midi } from '@tonejs/midi'
import { downloadUrl } from '../services/api'
import { getPianoSampler, getMasterLimiterNode, duckOnKick, resetBusLevels, applyMelodicFxPreset, setMasterTrimDb } from '../soundfonts/loader'
import { getPartInsert, resetPartInsert } from '../soundfonts/partInsert'
import { MELODIC_FX_PRESETS, fxFamilyFor, trimDbForStyle } from '../soundfonts/fxPresets'
import { makeSynthKit } from '../soundfonts/synthDrums'
import { makeHybridKit, makeBlendedKit, materializeSampleLayer, type KitSamplers } from '../soundfonts/customDrumKit'
import { getBassSampler, SAMPLED_BASS_VOICES } from '../soundfonts/bass'
import { getMelodicSamplerById, SAMPLED_VOICES } from '../soundfonts/melodic'
import { LayeredSampler } from '../soundfonts/layeredSampler'
import { resolvePartInstrument } from '../soundfonts/customInstruments'
import { useCustomInstruments } from './useCustomInstruments'
import { useSynthPatches } from './useSynthPatches'
import { useDrumKitPatches } from './useDrumKitPatches'
import { buildSynthFromPatch, type SynthPatch } from '../soundfonts/synthPatch'
import { voiceFor, setActiveStyle } from './useStyleCatalog'
import { startTicking as metroStart, stopTicking as metroStop, setMeter as metroSetMeter, countIn as metroCountIn } from './useMetronome'
import { SYNTH_STYLES, MELODIC_SYNTH_STYLES, PAD_STYLES, LOFI_STYLES, PLAYER_PARTS, type PlayerPart, CHANNEL_PART } from './playerConstants'
import { isRendering, offlineRenderRaw } from './useOfflineRender'
import type { AudioFormat } from '../utils/audioEncoder'
import { makeMelodyLead, makeSynthChords, makeArpPluck, makePad, makeStrings, makeSynthBass, makeLofiSynth } from '../soundfonts/synthVoices'
import { resolveMelodicVoiceKind, curveFromCC, type AutomationBreakpoint } from './voiceRouting'
import { drumTriggerCallback, voiceTriggerCallback } from './scheduler'

// Re-exported so existing importers keep getting these from useMidiPlayer.
export { PLAYER_PARTS, type PlayerPart } from './playerConstants'

export interface ParsedNote {
  midi: number
  time: number
  duration: number
  velocity: number
  isPercussion: boolean
}

export interface PartAutomation {
  volume: AutomationBreakpoint[]
  pan: AutomationBreakpoint[]
}

export interface MidiData {
  notes: ParsedNote[]
  duration: number
  automation: PartAutomation
}

/** A per-part stem is a single note track (plus a meta track), so flattening
 *  CC7/CC10 across every track — the same convention `notes` already uses — is
 *  safe: only the note-bearing track ever carries these events in practice. */
function parseAutomation(midi: Midi): PartAutomation {
  const volume: AutomationBreakpoint[] = []
  const pan: AutomationBreakpoint[] = []
  for (const track of midi.tracks) {
    volume.push(...curveFromCC(track.controlChanges?.[7]))
    pan.push(...curveFromCC(track.controlChanges?.[10]))
  }
  volume.sort((a, b) => a.time - b.time)
  pan.sort((a, b) => a.time - b.time)
  return { volume, pan }
}


// Global so only one track plays at a time
const currentlyPlaying = ref<string | null>(null)
const nowPlayingLabel = ref<string | null>(null)

// ── Cued track ───────────────────────────────────────────────────────────────
// What the docked transport plays when you press ▶ with nothing running. The
// view that owns a result (SongResult, ExportPanel) registers its own play
// routine here, so the transport is a real control rather than a readout that
// only lights up once playback has already started somewhere else.
const cuedLabel = ref<string | null>(null)
let cuedPlay: (() => void | Promise<void>) | null = null
const isLoading = ref(false)
const looping = ref(false)
const isRecording = ref(false)
// Per-part mute state, keyed by part name (matches backend _PART_CHANNELS).
const _allUnmuted = (): Record<PlayerPart, boolean> =>
  ({ drums: false, bass: false, chords: false, melody: false, arpeggio: false, pads: false, counter_melody: false })
const channelMuted = ref<Record<PlayerPart, boolean>>(_allUnmuted())
// A recorded audio clip (roadmap 9.4) has no MIDI channel, so it's muted via
// its own flag rather than folding into channelMuted/PLAYER_PARTS.
const audioClipMuted = ref(false)
function toggleAudioClipMute(): void {
  audioClipMuted.value = !audioClipMuted.value
  if (audioClipGain) audioClipGain.gain.value = audioClipMuted.value ? 0 : 1
}
// Per-part live level (0..1, default 1) — the control-surface fader mixer. Applied
// as velocity scaling at trigger time (see scheduler.ts), so it shapes live
// playback only; exports and offline renders stay at the written velocities.
const _allFull = (): Record<PlayerPart, number> =>
  ({ drums: 1, bass: 1, chords: 1, melody: 1, arpeggio: 1, pads: 1, counter_melody: 1 })
const partLevel = ref<Record<PlayerPart, number>>(_allFull())


// Cached single-note preview instruments for the piano-roll editor, keyed by
// "<styleId>:<part>". Built lazily from the same voice resolution as playback (minus
// custom instruments / panning) and kept for the session so key clicks are instant.
// A minimal structural voice surface — Tone.PolySynth / Tone.Sampler / MonoSynth /
// LayeredSampler all satisfy it. triggerAttack/triggerRelease drive live MIDI-in
// note-on/off (sustained), triggerAttackRelease drives the fixed-length click preview.
type AuditionVoice = {
  triggerAttackRelease: (n: string, d: number, t: number, v: number) => void
  triggerAttack: (n: string, t?: number, v?: number) => void
  // Note required so Tone.PolySynth/Sampler (whose `notes` arg is required) satisfy
  // it; the monophonic bass, which releases by time not note, is cast at the call site.
  triggerRelease: (n: string, t?: number) => void
}
type AuditionEntry =
  | { kind: 'voice'; inst: AuditionVoice; mono?: boolean }
  | { kind: 'drums'; kit: { trigger: (p: number, v: number, t: number) => void } }
const _auditionCache = new Map<string, AuditionEntry>()
// A `sustaining` preview only differs from the normal one when there's no style
// (live MIDI-in with nothing loaded → a held-note-friendly lead instead of the
// decaying piano), so it only forks the cache key in that case.
function _auditionKey(styleId: string | undefined, part: PlayerPart, sustaining: boolean): string {
  return `${styleId ?? ''}:${part}${sustaining && !styleId ? ':sus' : ''}`
}
// part → MIDI channel (inverse of CHANNEL_PART; drives voice choice for audition).
const _PART_CHANNEL: Record<PlayerPart, number> = {
  chords: 0, bass: 1, melody: 2, arpeggio: 3, pads: 4, counter_melody: 5, drums: 9,
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

// ── Live playback tempo ──────────────────────────────────────────────────────
// A non-destructive tempo nudge: the transport runs at `playbackBpm`, but the
// generated note data is never touched — this is playback speed only, so exports
// and re-rolls stay byte-identical. `generatedBpm` is the track's native tempo
// (0 = nothing loaded). Because Tone schedules the parts in ticks at the native
// tempo, the transport's real elapsed seconds scale by generatedBpm/playbackBpm;
// `tempoRatio` converts those back to native-time seconds so the seek bar, time
// readout, and editor playhead all stay aligned with the notes.
const MIN_PLAYBACK_BPM = 40
const MAX_PLAYBACK_BPM = 300
const generatedBpm = ref(0)
const playbackBpm = ref(0)
// native-time = transport-time × tempoRatio. 1 when un-nudged (byte-identical path).
const tempoRatio = computed(() =>
  generatedBpm.value > 0 && playbackBpm.value > 0 ? playbackBpm.value / generatedBpm.value : 1,
)
const isTempoNudged = computed(() =>
  generatedBpm.value > 0 && Math.round(playbackBpm.value) !== Math.round(generatedBpm.value),
)

function startPositionPolling() {
  stopPositionPolling()
  positionSeconds.value = 0
  _positionTimer = setInterval(() => {
    positionSeconds.value = Tone.getTransport().seconds * tempoRatio.value
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

// Instrument mode: 'samples' plays the confirmed-license sample sets where a voice
// has one (piano, vibraphone) and synthesizes the rest; 'synth' synthesizes every
// voice. Lets you A/B the sampled vs fully-synthetic sound, and is the seam a future
// "bring your own samples" feature plugs into. Persisted across sessions.
export type SampleMode = 'samples' | 'synth'
const _savedMode = typeof localStorage !== 'undefined'
  ? localStorage.getItem('genregrid_sample_mode')
  : null
const sampleMode = ref<SampleMode>(_savedMode === 'synth' ? 'synth' : 'samples')
function setSampleMode(mode: SampleMode) {
  sampleMode.value = mode
  if (typeof localStorage !== 'undefined') localStorage.setItem('genregrid_sample_mode', mode)
}

// Cache parsed MIDI data per URL so the piano roll persists after stop
const midiStore = ref<Record<string, MidiData>>({})

let scheduledParts: Tone.Part[] = []
// Per-play disposables — samplers and synths that are NOT globally cached
let disposables: Tone.ToneAudioNode[] = []
// Per-play user custom-instrument samplers (LayeredSampler isn't a ToneAudioNode)
let customSamplers: LayeredSampler[] = []
// Transport.schedule() ids for automation-curve ramps past the first breakpoint
// (roadmap 9.3) — cleared on stop so a stale callback can't ramp a disposed/
// reused insert on the next play.
let automationScheduleIds: number[] = []
// The current play's recorded-audio-clip insert (roadmap 9.4), if any — torn
// down by cleanup() via `disposables` like everything else; this reference is
// just so toggleAudioClipMute() can reach the live gain node.
let audioClipGain: Tone.Gain | null = null

function cleanup() {
  isPaused.value = false
  metroStop()   // clear the metronome's repeat before cancelling transport events
  Tone.getTransport().stop()
  Tone.getTransport().cancel()
  Tone.getTransport().loop = false
  resetBusLevels()   // never leave a sidechain duck applied after stop
  scheduledParts.forEach(p => p.dispose())
  disposables.forEach(d => d.dispose())
  customSamplers.forEach(s => s.dispose())
  automationScheduleIds.forEach(id => Tone.getTransport().clear(id))
  scheduledParts = []
  disposables = []
  customSamplers = []
  automationScheduleIds = []
  audioClipGain = null
  durationSeconds.value = 0
  stopPositionPolling()
  currentlyPlaying.value = null
  nowPlayingLabel.value = null
}

// Baked CC7 (volume)/CC10 (pan) curves (roadmap 9.3), applied to a part's
// persistent output insert. The first breakpoint sets the value immediately —
// exactly like the one-shot CC10 read this replaces, so an unautomated track
// (today's single default CC10 point) behaves identically. Any further
// breakpoints ramp in via Tone.getTransport().schedule(), keyed to the same
// seconds-at-native-tempo convention note times already use, so a live tempo
// nudge (7.6) stretches automation exactly like it already stretches notes.
const AUTOMATION_RAMP_SEC = 0.05
function scheduleAutomationTail(
  param: { linearRampToValueAtTime(value: number, time: number): unknown },
  curve: AutomationBreakpoint[],
  mapValue: (v: number) => number,
) {
  for (let i = 1; i < curve.length; i++) {
    const point = curve[i]
    const id = Tone.getTransport().schedule((time) => {
      param.linearRampToValueAtTime(mapValue(point.value), time + AUTOMATION_RAMP_SEC)
    }, point.time)
    automationScheduleIds.push(id)
  }
}
function applyPartAutomation(part: PlayerPart, volumeCurve: AutomationBreakpoint[], panCurve: AutomationBreakpoint[]) {
  const insert = getPartInsert(part)
  if (volumeCurve.length) insert.gain.gain.value = volumeCurve[0].value
  scheduleAutomationTail(insert.gain.gain, volumeCurve, v => v)
  if (panCurve.length) insert.panner.pan.value = panCurve[0].value * 2 - 1
  scheduleAutomationTail(insert.panner.pan, panCurve, v => v * 2 - 1)
}

export function useMidiPlayer() {
  async function toggle(url: string, styleId?: string, label?: string, loop?: boolean,
                        loopRegion?: { start: number; end: number },
                        audioClip?: { url: string; offsetSeconds: number } | null) {
    if (currentlyPlaying.value === url) {
      cleanup()
      return
    }

    cleanup()
    // A loop-mode clip should repeat when you press play; a full song/arrangement
    // should play through. Callers that know which they're starting pass `loop`;
    // undefined leaves the transport's manual loop toggle untouched. The play
    // path below reads `looping.value` to set the transport loop points.
    if (loop !== undefined) looping.value = loop
    const token = ++_playToken
    isLoading.value = true
    nowPlayingLabel.value = label ?? url.split('/').pop() ?? url
    setActiveStyle(styleId)   // the Instruments panel opens on what you're hearing

    try {
      await Tone.start()
      if (token !== _playToken) return
      console.log(`[play] Tone.start OK — ctx=${Tone.getContext().state} rate=${Tone.getContext().rawContext.sampleRate} style=${styleId ?? 'none'}`)

      applyVolume(volume.value)
      console.log(`[play] volume applied: destVol=${Tone.getDestination().volume.value.toFixed(1)}dB`)

      // Every part's output insert (roadmap 9.3) is a persistent node reused across
      // plays — reset it to flat/centered now so a previous song's automation can't
      // bleed into this one before this song's own static pan / automation is applied.
      for (const p of PLAYER_PARTS) resetPartInsert(p)

      const isSynth        = styleId ? SYNTH_STYLES.has(styleId) : false
      const isMelodicSynth = styleId ? MELODIC_SYNTH_STYLES.has(styleId) : false
      const isPad          = styleId ? PAD_STYLES.has(styleId) : false
      const isLofi         = styleId ? LOFI_STYLES.has(styleId) : false

      // Retune the shared melodic FX chain + master loudness trim to this style's
      // family, so each genre sits in its own space and at an even level. Kicked off
      // here (may regenerate the reverb IR) and awaited before parts are scheduled.
      const fxFamily = fxFamilyFor({ isPad, isLofi, isSynth, isMelodicSynth })
      const fxReady = applyMelodicFxPreset(MELODIC_FX_PRESETS[fxFamily])
      setMasterTrimDb(trimDbForStyle(styleId, fxFamily))

      // Pre-load all samplers + MIDI in parallel.
      // SYNTH_STYLES use synthesis for drums + bass — skip those sampler loads entirely.
      //
      // Instrument-identity voices (Phase 3): each part names its playback voice
      // via the style's instrumentation (the registry, served in /styles →
      // voices.*). Sampled voices ("electric_piano_1") load a sampler per part;
      // non-sampled voices ("melody_lead", "pad_synth") map to synth families
      // below. The registry is the single source of truth — no per-style map here.
      const _partVoice = {
        chords: voiceFor(styleId, 'chords'),
        melody: voiceFor(styleId, 'melody'),
        arpeggio: voiceFor(styleId, 'arpeggio'),
      }
      // 'synth' mode skips every sampler load, so the existing synth fallbacks below
      // take over for all voices. In 'samples' mode a voice loads a sampler only if it
      // has a confirmed-license set (SAMPLED_VOICES / SAMPLED_BASS_VOICES); everything
      // else still synthesizes.
      const useSamples = sampleMode.value === 'samples'
      const _samplerP = (v: string | null, part: PlayerPart) =>
        (useSamples && v ? getMelodicSamplerById(v, part, getPartInsert(part).gain) : null) ?? Promise.resolve(null)
      const _bassVoice = voiceFor(styleId, 'bass')
      const _bassSampled = useSamples && !isSynth && !!_bassVoice && SAMPLED_BASS_VOICES.has(_bassVoice)

      const fetchUrl = url.startsWith('blob:') || url.startsWith('data:') ? url : downloadUrl(url)
      const [buf, bassSampler, chordsSamp, melodySamp, arpSamp] = await Promise.all([
        fetch(fetchUrl).then(r => r.arrayBuffer()),
        _bassSampled ? getBassSampler(_bassVoice) : Promise.resolve(null),
        _samplerP(_partVoice.chords, 'chords'),
        _samplerP(_partVoice.melody, 'melody'),
        _samplerP(_partVoice.arpeggio, 'arpeggio'),
      ])

      // The Salamander grand piano is the last-resort chords/melody voice, needed
      // only when a part has no sampled voice and no synth family fits. Each part
      // that needs it loads its OWN piano instance (see getPianoSampler) — decided
      // only now, since it depends on whether that part's sampler actually resolved.
      const pianoEligible = useSamples && !isSynth && !isPad && !isLofi && !isMelodicSynth
      const [chordsPiano, melodyPiano] = await Promise.all([
        (pianoEligible && !chordsSamp) ? getPianoSampler('chords', getPartInsert('chords').gain) : Promise.resolve(null),
        (pianoEligible && !melodySamp) ? getPianoSampler('melody', getPartInsert('melody').gain) : Promise.resolve(null),
      ])

      if (token !== _playToken) return

      await fxReady            // reverb IR ready before the first note is scheduled
      if (token !== _playToken) return

      // Load any user custom instruments assigned to this style's parts. Every part
      // can be user-sampled; a custom assignment overrides that part's built-in voice.
      const customByPart: Partial<Record<PlayerPart, LayeredSampler>> = {}
      const customKit: KitSamplers = new Map()
      if (useSamples) {
        const ci = useCustomInstruments()
        if (ci.supported()) {
          await ci.ensureLoaded()
          const parts: PlayerPart[] = ['chords', 'bass', 'melody', 'arpeggio', 'pads', 'counter_melody']
          await Promise.all(parts.map(async (part) => {
            const r = resolvePartInstrument(ci.assignments.value, styleId, part, null)
            if (r.source !== 'custom') return
            const manifest = await ci.materialize(r.id)
            if (!manifest || manifest.layers.length === 0) return
            const ls = new LayeredSampler({ baseUrl: '', manifest, volume: -6 })
            await ls.loaded
            ls.connect(getPartInsert(part).gain)
            customByPart[part] = ls
            customSamplers.push(ls)
          }))

          // Drums resolve the same way but load as a kit: one single-zone sampler per
          // mapped piece, so nothing is ever pitch-shifted and unmapped pieces stay
          // synthesized (see makeHybridKit).
          const drumChoice = resolvePartInstrument(ci.assignments.value, styleId, 'drums', null)
          if (drumChoice.source === 'custom') {
            const kit = await ci.materializeKit(drumChoice.id)
            await Promise.all(Object.entries(kit ?? {}).map(async ([pitch, manifest]) => {
              if (!manifest.layers.length) return
              const ls = new LayeredSampler({ baseUrl: '', manifest, volume: -4 })
              await ls.loaded
              ls.connect(getPartInsert('drums').gain)
              customKit.set(Number(pitch), ls)
              customSamplers.push(ls)
            }))
          }
          if (token !== _playToken) return
        }
      }

      // User-designed synth patches assigned to melodic parts (pure JSON, no IPC, so
      // resolved synchronously and in any sample mode). A patch wins over the built-in
      // voice for its part — see resolveMelodicVoiceKind. Built lazily in getMelodicInstrument.
      const patchByPart: Partial<Record<PlayerPart, SynthPatch>> = {}
      {
        const sp = useSynthPatches()
        for (const part of ['chords', 'bass', 'melody', 'arpeggio', 'pads', 'counter_melody'] as PlayerPart[]) {
          const p = sp.resolvePatchForPart(styleId, part)
          if (p) patchByPart[part] = p
        }
      }

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
      midiStore.value[url] = { notes: allNotes, duration: midi.duration, automation: parseAutomation(midi) }

      // A new track loads at its native tempo, clearing any prior live nudge —
      // the previous track's override doesn't carry to a different song.
      const nativeBpm = midi.header.tempos[0]?.bpm ?? 120
      generatedBpm.value = nativeBpm
      playbackBpm.value = nativeBpm
      Tone.getTransport().bpm.value = nativeBpm
      // Meter for the metronome click grid (accent per bar); default 4/4.
      const ts = midi.header.timeSignatures[0]?.timeSignature
      metroSetMeter(ts?.[0] ?? 4, ts?.[1] ?? 4)

      // Synthesized drum kit — one voice per articulation, tuned to the style's
      // character. Replaces the old thin/fake-cymbal samples for every genre.
      // A user kit assigned to the drums part layers over this per piece (below).
      // Routed through the drums part insert (roadmap 9.3), not the bus directly.
      const resolvedDrumPatch = useDrumKitPatches().resolveKitForStyle(styleId)
      const synthDrumKit = makeSynthKit(resolvedDrumPatch, getPartInsert('drums').gain)
      disposables.push(...synthDrumKit.nodes)
      // The kit's own "sample base" (Drum Designer) blends UNDER the synth first —
      // then a style-assigned sample kit (loaded above) still wins per piece outright,
      // so a two-piece kit is usable without filling every slot.
      const patchSamplers = await materializeSampleLayer(
        useCustomInstruments(), resolvedDrumPatch.sampleKitId, getPartInsert('drums').gain,
      )
      customSamplers.push(...patchSamplers.values())
      const blendedDrumKit = makeBlendedKit(synthDrumKit, patchSamplers, resolvedDrumPatch.sampleBlend)
      const drumKit = makeHybridKit(blendedDrumKit, customKit)
      let _synthBass: Tone.MonoSynth | null = null
      const getSynthBass = () => { if (!_synthBass) _synthBass = makeSynthBass(disposables, getPartInsert('bass').gain); return _synthBass }

      // Melodic voices are resolved per part (chords / melody / arpeggio) so they
      // no longer share one timbre. Every voice — synth, sampler, or the piano
      // fallback — connects through that part's persistent insert (roadmap 9.3).
      // The insert's pan/gain are set uniformly for every part by
      // applyPartAutomation below, once per track — not here.
      const voiceCache: Record<number, Tone.PolySynth | LayeredSampler> = {}

      function makePanned(build: (out: Tone.ToneAudioNode) => Tone.PolySynth, part: PlayerPart): Tone.PolySynth {
        return build(getPartInsert(part).gain)
      }

      // channel 0 = chords, 2 = melody, 3 = arpeggio, 4 = pads,
      // 5 = counter-melody (see backend _PART_CHANNELS)
      function getMelodicInstrument(channel: number): Tone.PolySynth | LayeredSampler {
        if (voiceCache[channel]) return voiceCache[channel]

        const part = CHANNEL_PART[channel]
        const patch = patchByPart[part]
        const custom = customByPart[part]
        // A sampled (identity) voice loaded for this part, and the resolved voice id
        // (only chords/melody/arp carry these; other channels have none).
        const sampler = ({ 0: chordsSamp, 2: melodySamp, 3: arpSamp } as Record<number, LayeredSampler | null>)[channel] ?? null
        const voiceId = ({ 0: _partVoice.chords, 2: _partVoice.melody, 3: _partVoice.arpeggio } as Record<number, string | null>)[channel] ?? null
        const piano = ({ 0: chordsPiano, 2: melodyPiano } as Record<number, LayeredSampler | null>)[channel] ?? null

        // Pure decision (see voiceRouting.ts) — construction stays here.
        const kind = resolveMelodicVoiceKind({
          channel, hasPatch: !!patch, hasCustom: !!custom, hasSampler: !!sampler, voiceId,
          isLofi, isSynth, isMelodicSynth, isPad, hasPiano: !!piano,
        })
        let inst: Tone.PolySynth | LayeredSampler
        switch (kind) {
          case 'synth_patch':      inst = makePanned((out) => buildSynthFromPatch(patch!, disposables, out) as Tone.PolySynth, part); break
          case 'custom':           inst = custom!; break
          case 'sampler':          inst = sampler!; break
          case 'piano':            inst = piano!; break               // this part's own Salamander grand instance
          case 'pad':              inst = makePanned((out) => makePad(disposables, out), part); break
          case 'strings':          inst = makePanned((out) => makeStrings(disposables, out), part); break
          case 'arp_pluck':        inst = makePanned((out) => makeArpPluck(disposables, out), part); break
          case 'lofi':             inst = makePanned((out) => makeLofiSynth(disposables, out), part); break
          case 'synth_chords':     inst = makePanned((out) => makeSynthChords(disposables, out), part); break
          case 'melody_lead_soft': inst = makePanned((out) => makeMelodyLead(true, disposables, out), part); break
          case 'synth_lead':       inst = makePanned((out) => makeMelodyLead(false, disposables, out), part); break
          default: { const _never: never = kind; throw new Error(`unreachable voice kind: ${_never}`) }
        }
        voiceCache[channel] = inst
        return inst
      }

      const midiToNote = (m: number) => Tone.Frequency(m, 'midi').toNote()
      for (const track of midi.tracks) {
        if (track.notes.length === 0) continue

        const channel = track.channel ?? 0
        const isPerc = track.instrument.percussion || channel === 9
        // Baked volume/pan curves (roadmap 9.3) — applied uniformly to every part's
        // insert regardless of which branch below builds its voice.
        const automationPart = CHANNEL_PART[channel]
        if (automationPart) {
          applyPartAutomation(automationPart, curveFromCC(track.controlChanges?.[7]), curveFromCC(track.controlChanges?.[10]))
        }

        if (isPerc) {
          // Electronic styles get a sidechain pump: each kick briefly ducks the
          // melodic and bass buses so the mix breathes around the four-on-the-floor.
          const notes = track.notes.map(n => ({ time: n.time, midi: n.midi, velocity: n.velocity }))
          const part = new Tone.Part<{ time: number; midi: number; velocity: number }>(
            drumTriggerCallback(drumKit, () => channelMuted.value.drums, isSynth, duckOnKick,
              () => partLevel.value.drums), notes)
          part.start(0)
          scheduledParts.push(part)

        } else if (channel === 1) {
          // Bass — a designed patch wins, then a user custom instrument, then a sampled
          // voice (samples mode + confirmed-license set), otherwise the synth bass.
          const bassInst = (patchByPart.bass ? buildSynthFromPatch(patchByPart.bass, disposables, getPartInsert('bass').gain) : null)
            ?? customByPart.bass ?? bassSampler ?? getSynthBass()
          const notes = track.notes.map(n => ({
            time: n.time, midi: n.midi, duration: n.duration, velocity: n.velocity,
          }))
          const part = new Tone.Part<{ time: number; midi: number; duration: number; velocity: number }>(
            voiceTriggerCallback(bassInst, () => channelMuted.value.bass, midiToNote,
              () => partLevel.value.bass), notes)
          part.start(0)
          scheduledParts.push(part)

        } else {
          // Chords, melody, arpeggio — distinct style-aware voice per part, each
          // placed in the stereo field by applyPartAutomation above.
          const instrument = getMelodicInstrument(channel)
          const notes = track.notes.map(n => ({
            time: n.time, midi: n.midi, duration: n.duration, velocity: n.velocity,
          }))
          const mutePart = CHANNEL_PART[channel] ?? 'chords'
          const part = new Tone.Part<{ time: number; midi: number; duration: number; velocity: number }>(
            voiceTriggerCallback(instrument, () => channelMuted.value[mutePart], midiToNote,
              () => partLevel.value[mutePart]), notes)
          part.start(0)
          scheduledParts.push(part)
        }
      }

      console.log(`[play] built graph — tracks=${midi.tracks.length} parts=${scheduledParts.length} disposables=${disposables.length} duration=${midi.duration.toFixed(2)}s bpm=${Tone.getTransport().bpm.value}`)

      // A recorded audio clip (roadmap 9.4) — a raw buffer placed at a fixed
      // transport offset, independent of the MIDI-triggered synthesis graph
      // above. `.sync()` binds start/stop to the transport clock, so it
      // follows loop/seek/tempo-nudge behavior the same as everything else,
      // with no bars/beats math of its own to keep in step.
      if (audioClip) {
        try {
          const clipPlayer = new Tone.Player(audioClip.url)
          await Tone.loaded()
          if (token !== _playToken) { clipPlayer.dispose(); return }
          const panner = new Tone.Panner(0).toDestination()
          const gain = new Tone.Gain(audioClipMuted.value ? 0 : 1).connect(panner)
          clipPlayer.connect(gain)
          clipPlayer.sync().start(audioClip.offsetSeconds)
          audioClipGain = gain
          disposables.push(clipPlayer, gain, panner)
        } catch (e) {
          console.warn('[play] audio clip failed to load — continuing without it', e)
        }
      }

      durationSeconds.value = midi.duration
      currentlyPlaying.value = url

      // An explicit loop region (the piano-roll editor's loop band) wins over the
      // whole-clip loop toggle: play only the selected span, repeating.
      if (loopRegion && loopRegion.end > loopRegion.start) {
        Tone.getTransport().loop = true
        Tone.getTransport().loopStart = Math.max(0, loopRegion.start)
        Tone.getTransport().loopEnd = loopRegion.end
        Tone.getTransport().seconds = Math.max(0, loopRegion.start)
      } else if (looping.value) {
        Tone.getTransport().loop = true
        Tone.getTransport().loopStart = 0
        Tone.getTransport().loopEnd = midi.duration
      } else {
        Tone.getTransport().loop = false
      }

      Tone.getTransport().start()
      metroStart()   // click along if the metronome is on (re-scheduled after the cancel above)
      console.log(`[play] transport started — state=${Tone.getTransport().state} seconds=${Tone.getTransport().seconds.toFixed(2)} loop=${looping.value}`)
      startPositionPolling()

      if (!looping.value && !(loopRegion && loopRegion.end > loopRegion.start)) {
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

  // ── Note audition (piano-roll editor key / insert preview) ──────────────────
  // Build (once) a preview instrument for a style's part, reusing the same voice
  // resolution playback uses. Custom instruments and per-part panning are skipped —
  // a single-note preview doesn't need them — so this can differ slightly from the
  // mixed playback voice, which is an acceptable trade for instant feedback.
  async function _buildAudition(styleId: string | undefined, part: PlayerPart,
                                sustaining = false): Promise<AuditionEntry> {
    const key = _auditionKey(styleId, part, sustaining)
    const cached = _auditionCache.get(key)
    if (cached) return cached
    // With no style loaded, prefer a sustaining lead over the decaying piano so a
    // held MIDI key rings out — but only in that no-context case; a loaded style
    // still auditions its real voice (which may legitimately decay).
    const susFallback = sustaining && !styleId

    const isSynth = styleId ? SYNTH_STYLES.has(styleId) : false
    const isMelodicSynth = styleId ? MELODIC_SYNTH_STYLES.has(styleId) : false
    const isPad = styleId ? PAD_STYLES.has(styleId) : false
    const isLofi = styleId ? LOFI_STYLES.has(styleId) : false
    const useSamples = sampleMode.value === 'samples'
    const nodes: Tone.ToneAudioNode[] = []
    let entry: AuditionEntry

    if (part === 'drums') {
      const synthKit = makeSynthKit(useDrumKitPatches().resolveKitForStyle(styleId), getPartInsert('drums').gain)
      entry = { kind: 'drums', kit: makeHybridKit(synthKit, new Map()) }
    } else if (part === 'bass') {
      const bassVoice = voiceFor(styleId, 'bass')
      const sampler = (useSamples && !isSynth && bassVoice && SAMPLED_BASS_VOICES.has(bassVoice))
        ? await getBassSampler(bassVoice) : null
      // The synth bass is a monophonic MonoSynth (releases the single voice, not by
      // note); the sampled bass releases per-note like the melodic voices.
      entry = { kind: 'voice', inst: sampler ?? makeSynthBass(nodes, getPartInsert('bass').gain), mono: !sampler }
    } else {
      const channel = _PART_CHANNEL[part] ?? 0
      const voiceId = voiceFor(styleId, part)
      const insertGain = getPartInsert(part).gain
      const sampler = (useSamples && voiceId && SAMPLED_VOICES.has(voiceId))
        ? await getMelodicSamplerById(voiceId, part, insertGain) : null
      const piano = (useSamples && !isSynth && !isPad && !isLofi && !isMelodicSynth && !sampler
        && !susFallback && (part === 'chords' || part === 'melody')) ? await getPianoSampler(part, insertGain) : null
      const kind = resolveMelodicVoiceKind({
        channel, hasPatch: false, hasCustom: false, hasSampler: !!sampler, voiceId,
        isLofi, isSynth, isMelodicSynth, isPad, hasPiano: !!piano,
      })
      const bus = insertGain
      let inst: Tone.PolySynth | LayeredSampler
      switch (kind) {
        case 'sampler':          inst = sampler!; break
        case 'piano':            inst = piano!; break
        case 'pad':              inst = makePad(nodes, bus); break
        case 'strings':          inst = makeStrings(nodes, bus); break
        case 'arp_pluck':        inst = makeArpPluck(nodes, bus); break
        case 'lofi':             inst = makeLofiSynth(nodes, bus); break
        case 'synth_chords':     inst = makeSynthChords(nodes, bus); break
        case 'melody_lead_soft': inst = makeMelodyLead(true, nodes, bus); break
        case 'synth_lead':       inst = makeMelodyLead(false, nodes, bus); break
        default:                 inst = makeMelodyLead(true, nodes, bus); break   // incl. 'custom' (no custom in preview)
      }
      entry = { kind: 'voice', inst }
    }
    _auditionCache.set(key, entry)
    return entry
  }

  /** Warm the preview instrument so the first key click sounds instantly. Pass
   *  `sustaining` to warm the live-play (held-note) voice used by MIDI-in. */
  function prepareAudition(styleId: string | undefined, part: PlayerPart, sustaining = false) {
    _buildAudition(styleId, part, sustaining).catch(e => console.warn('[audition] prepare failed', e))
  }

  /** Play a single pitch on the part's instrument (editor key / note preview). */
  async function audition(styleId: string | undefined, part: PlayerPart, midi: number,
                          durationSec = 0.4, velocity = 0.9) {
    try {
      await Tone.start()
      applyVolume(volume.value)
      const entry = await _buildAudition(styleId, part)
      const t = Tone.now()
      if (entry.kind === 'drums') entry.kit.trigger(midi, velocity, t)
      else entry.inst.triggerAttackRelease(Tone.Frequency(midi, 'midi').toNote(), durationSec, t, velocity)
    } catch (e) {
      console.warn('[audition] failed', e)
    }
  }

  /** Schedule a one-shot on the already-prepared (cached) audition voice at an
   *  absolute transport/context time. Used by the piano-roll editor to replay
   *  loop-recorded overdubs on each pass without reloading the player. No-ops if the
   *  voice isn't built yet — callers prepareAudition() first (the editor does on open). */
  function scheduleAudition(styleId: string | undefined, part: PlayerPart, midi: number,
                            time: number, durationSec = 0.4, velocity = 0.9) {
    const entry = _auditionCache.get(_auditionKey(styleId, part, false))
    if (!entry) return
    if (entry.kind === 'drums') entry.kit.trigger(midi, velocity, time)
    else entry.inst.triggerAttackRelease(Tone.Frequency(midi, 'midi').toNote(), durationSec, time, velocity)
  }

  /** Note-on for a sustained audition (a live MIDI controller): the note rings until
   *  auditionOff. Drums are one-shot, so a note-on triggers the hit and note-off no-ops. */
  async function auditionOn(styleId: string | undefined, part: PlayerPart, midi: number, velocity = 0.9) {
    try {
      await Tone.start()
      applyVolume(volume.value)
      // `sustaining` so a held note rings when no style is loaded (see _buildAudition).
      const entry = await _buildAudition(styleId, part, true)
      // Live input wants the note NOW — trigger at the raw context time (immediate),
      // not Tone.now() which adds the ~100ms scheduler look-ahead meant for playback.
      const t = Tone.immediate()
      if (entry.kind === 'drums') entry.kit.trigger(midi, velocity, t)
      else entry.inst.triggerAttack(Tone.Frequency(midi, 'midi').toNote(), t, velocity)
    } catch (e) {
      console.warn('[audition] note-on failed', e)
    }
  }

  /** Note-off for a sustained audition. Uses the already-built (cached) voice; a
   *  mono voice releases its single note, a poly voice releases the matching pitch. */
  function auditionOff(styleId: string | undefined, part: PlayerPart, midi: number) {
    const entry = _auditionCache.get(_auditionKey(styleId, part, true))
    if (!entry || entry.kind === 'drums') return
    try {
      const t = Tone.immediate()   // release now, without the playback look-ahead
      // Mono voice (MonoSynth): triggerRelease takes a time, not a note.
      if (entry.mono) (entry.inst as unknown as { triggerRelease: (time?: number) => void }).triggerRelease(t)
      else entry.inst.triggerRelease(Tone.Frequency(midi, 'midi').toNote(), t)
    } catch (e) {
      console.warn('[audition] note-off failed', e)
    }
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

      // Tap the post-limiter node so the recording captures exactly what's heard
      // (the master's soft-clip limiter included), not the pre-limiter mix.
      const comp = getMasterLimiterNode()
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

  // Render a WAV (the parallel per-part offline render lives in useOfflineRender).
  // Pause live playback first: the render walks the timeline on the main thread and
  // would otherwise starve the Transport's lookahead scheduler, freezing playback
  // mid-export. The render is offline/position-independent, so pausing doesn't change
  // the exported audio; playback holds its spot to resume from.
  async function offlineRender(
    url: string,
    styleId: string | undefined,
    durationSeconds: number,
    channelFilter: 'all' | 'melodic' | PlayerPart = 'all',
    onProgress?: (v: number) => void,
    format: AudioFormat = 'wav',
    audioClip?: { url: string; offsetSeconds: number } | null,
  ): Promise<Blob> {
    if (currentlyPlaying.value !== null && !isPaused.value) {
      Tone.getTransport().pause()
      isPaused.value = true
    }
    return offlineRenderRaw(url, styleId, durationSeconds, channelFilter, onProgress, format, audioClip)
  }

  function stop() {
    cleanup()
  }

  function getMidiData(url: string): MidiData | null {
    return midiStore.value[url] ?? null
  }

  /** Replace the cached piano-roll data for a URL — call after a save so a reopened
   *  editor reads the edited notes (prefetchMidi is a no-op once a URL is cached). */
  function setMidiData(url: string, data: MidiData): void {
    midiStore.value[url] = data
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
      midiStore.value[url] = { notes: allNotes, duration: midi.duration, automation: parseAutomation(midi) }
    } catch {
      // silently ignore — piano roll will appear once the user hits play instead
    }
  }

  function toggleMute(ch: PlayerPart) {
    channelMuted.value = { ...channelMuted.value, [ch]: !channelMuted.value[ch] }
  }

  /** Live per-part level (0..1) — driven by control-surface faders. */
  function setPartLevel(ch: PlayerPart, v: number) {
    partLevel.value = { ...partLevel.value, [ch]: Math.max(0, Math.min(1, v)) }
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
    // `seconds` is native-time (what the seek bar shows); the transport runs in
    // real-time, so divide by the ratio to land on the right musical position.
    if (currentlyPlaying.value === null) return
    const native = Math.max(0, seconds)
    Tone.getTransport().seconds = native / tempoRatio.value
    positionSeconds.value = native   // snap the playhead immediately
  }

  /** Non-destructive live tempo — sets the transport speed only; note data,
   *  exports, and re-rolls are untouched. No-op until a track is loaded. */
  function setPlaybackBpm(bpm: number) {
    if (generatedBpm.value <= 0) return
    const b = Math.round(Math.max(MIN_PLAYBACK_BPM, Math.min(MAX_PLAYBACK_BPM, bpm)))
    playbackBpm.value = b
    Tone.getTransport().bpm.value = b
  }

  /** Return the transport to the track's generated tempo. */
  function resetPlaybackBpm() {
    if (generatedBpm.value > 0) setPlaybackBpm(generatedBpm.value)
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

  /** Register (or clear, with nulls) what the transport's ▶ starts when idle. */
  function cue(label: string | null, play: (() => void | Promise<void>) | null) {
    cuedLabel.value = label
    cuedPlay = play
  }

  async function playCued() {
    if (!cuedPlay) return
    // Count-in (if set): click a lead-in, then start the track when it finishes.
    await metroCountIn()
    await cuedPlay()
  }

  /** One master play/pause toggle, shared by the transport ▶/⏸ button and the Space key:
   *  start the cued track when idle, otherwise pause/resume in place. */
  async function playPause() {
    const idle = currentlyPlaying.value === null && !isLoading.value
    if (idle) await playCued()
    else togglePause()
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
    // Synth/pad/lofi styles use in-memory oscillators — nothing to fetch; and 'synth'
    // mode never loads samplers. Drums are synthesized for every style now, so only
    // the confirmed-license bass/melodic sets warm here.
    if (isSynth || isPad || isLofi || sampleMode.value !== 'samples') return
    // Warm the registry-selected sample sets for this style (best-effort), each
    // through its part's own insert so the warmed instance is already wired the
    // way real playback will use it.
    const melodicVoices = (['chords', 'melody', 'arpeggio'] as const)
      .map(part => ({ part, voiceId: voiceFor(styleId, part) }))
      .filter((v): v is { part: 'chords' | 'melody' | 'arpeggio'; voiceId: string } => !!v.voiceId && SAMPLED_VOICES.has(v.voiceId))
    const bassVoice = voiceFor(styleId, 'bass')
    const bassP = bassVoice && SAMPLED_BASS_VOICES.has(bassVoice) ? [getBassSampler(bassVoice)] : []
    Promise.all([
      ...bassP,
      ...melodicVoices.map(({ part, voiceId }) => getMelodicSamplerById(voiceId, part, getPartInsert(part).gain)),
    ]).catch(() => { /* best-effort, ignore network errors */ })
  }

  return { toggle, stop, currentlyPlaying, nowPlayingLabel, isLoading, getMidiData, prefetchMidi, prefetchSamplers, volume, setVolume, sampleMode, setSampleMode, looping, setLooping, isRecording, exportAudio, offlineRender, isRendering, channelMuted, toggleMute, soloPart, partLevel, setPartLevel, seek, positionSeconds, durationSeconds, isPlayingUrl, isPaused, togglePause, cue, playCued, playPause, cuedLabel, prepareAudition, audition, scheduleAudition, auditionOn, auditionOff, setMidiData, generatedBpm, playbackBpm, tempoRatio, isTempoNudged, setPlaybackBpm, resetPlaybackBpm, audioClipMuted, toggleAudioClipMute }
}
