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

// Offline WAV export — renders each part on its own OfflineAudioContext
// concurrently (separate Chromium threads), sums them, and applies the master
// limiter once. Split out of useMidiPlayer.ts; the pause-live-playback wrapper
// stays there (it owns the playback refs). See docs/roadmap.md Phase 3.
import { ref } from 'vue'
import * as Tone from 'tone'
import { Midi } from '@tonejs/midi'
import { downloadUrl } from '../services/api'
import { makeMasterLimiter, softClipCurve } from '../soundfonts/loader'
import { resolveToneValues, saturationCurve } from '../soundfonts/partTone'
import { useMixSettings } from './useMixSettings'
import { makeSynthKit } from '../soundfonts/synthDrums'
import { makeHybridKit, makeBlendedKit, materializeSampleLayer, type KitSamplers } from '../soundfonts/customDrumKit'
import { LayeredSampler } from '../soundfonts/layeredSampler'
import { resolvePartInstrument } from '../soundfonts/customInstruments'
import { buildSynthFromPatch, type SynthPatch } from '../soundfonts/synthPatch'
import { useSynthPatches } from './useSynthPatches'
import { useCustomInstruments } from './useCustomInstruments'
import { useDrumKitPatches } from './useDrumKitPatches'
import { voiceFor } from './useStyleCatalog'
import { encodeAudio, type AudioFormat } from '../utils/audioEncoder'
import { PLAYER_PARTS, type PlayerPart, CHANNEL_PART, SYNTH_STYLES, PAD_STYLES, LOFI_STYLES, MELODIC_SYNTH_STYLES } from './playerConstants'
import { fxFamilyFor, trimDbForStyle } from '../soundfonts/fxPresets'
import { curveFromCC, type AutomationBreakpoint } from './voiceRouting'
import { placeClipInMix } from '../utils/audioClip'

// A part's drawn CC7/CC10 curve, scheduled directly onto its insert's gain/pan
// AudioParam. Unlike live playback (see useMidiPlayer.ts's applyPartAutomation)
// this needs no ramp-duration fudge factor or Transport scheduling: an offline
// render is fully deterministic ahead of time, so each breakpoint after the
// first can be a true linearRampToValueAtTime from the previous value.
function scheduleOfflineAutomationTail(
  param: { linearRampToValueAtTime(value: number, time: number): unknown },
  curve: AutomationBreakpoint[],
  mapValue: (v: number) => number,
) {
  for (let i = 1; i < curve.length; i++) {
    param.linearRampToValueAtTime(mapValue(curve[i].value), curve[i].time)
  }
}

// True while any WAV export is rendering (drives the export progress UI).
export const isRendering = ref(false)

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

// Does the parsed MIDI carry any notes for a given part? Mirrors the render's own
// channel→voice routing (percussion / ch9 → drums; everything else via CHANNEL_PART,
// with unknown non-perc channels falling through to chords like the scheduler does).
// Used to decide which parts to spin up as parallel per-part renders.
export function partHasNotes(midi: Midi, part: PlayerPart): boolean {
  return midi.tracks.some(t => {
    if (t.notes.length === 0) return false
    const perc = t.instrument.percussion || (t.channel ?? 0) === 9
    const p = perc ? 'drums' : CHANNEL_PART[t.channel ?? 0] ?? 'chords'
    return p === part
  })
}

// Sum several rendered part buffers into one stereo pair. Pure (no Web Audio), so it's
// unit-testable. The per-part offline graphs never share nodes, so summing their outputs
// reproduces exactly the signal the single-pass graph summed at its master bus — the
// pre-limiter mix. Exported for the mix-identity test.
export function sumPartBuffers(
  buffers: Array<Pick<AudioBuffer, 'length' | 'sampleRate' | 'numberOfChannels' | 'getChannelData'>>,
): { length: number; sampleRate: number; channels: [Float32Array<ArrayBuffer>, Float32Array<ArrayBuffer>] } {
  const length = buffers.reduce((m, b) => Math.max(m, b.length), 0)
  const sampleRate = buffers[0]?.sampleRate ?? 44100
  const L = new Float32Array(length)
  const R = new Float32Array(length)
  for (const b of buffers) {
    const bl = b.getChannelData(0)
    const br = b.numberOfChannels > 1 ? b.getChannelData(1) : bl
    for (let i = 0; i < b.length; i++) { L[i] += bl[i]; R[i] += br[i] }
  }
  return { length, sampleRate, channels: [L, R] }
}

// Sum the parallel per-part renders and apply the master soft-clip limiter ONCE, in a
// raw Web-Audio pass. The limiter is non-linear, so it must run on the summed mix, not
// per part. A raw WaveShaperNode reproduces makeMasterLimiter exactly: Tone samples the
// `mapping` over [-1, 1] into `length` points (curve[i] = softClipCurve(i/(len-1)*2-1))
// and sets oversample '4x' — so the parallel path's output is bit-for-bit the single-
// pass path's, minus float summation order (inaudible).
async function limitMix(
  buffers: Array<Pick<AudioBuffer, 'length' | 'sampleRate' | 'numberOfChannels' | 'getChannelData'>>,
): Promise<AudioBuffer> {
  const { length, sampleRate, channels } = sumPartBuffers(buffers)
  const ctx = new OfflineAudioContext(2, length, sampleRate)
  const mix = ctx.createBuffer(2, length, sampleRate)
  mix.copyToChannel(channels[0], 0)
  mix.copyToChannel(channels[1], 1)
  const src = ctx.createBufferSource()
  src.buffer = mix
  const ws = ctx.createWaveShaper()
  const curve = new Float32Array(4096)
  for (let i = 0; i < 4096; i++) curve[i] = softClipCurve((i / 4095) * 2 - 1)
  ws.curve = curve
  ws.oversample = '4x'
  // Master EQ (roadmap 6.5), raw BiquadFilterNodes mirroring loader.ts's live
  // masterOut → EQ → limiter chain — this multi-part summed-mix pass has no Tone
  // context, same reason the limiter above is hand-reconstructed rather than reused.
  const { low, mid, high } = useMixSettings().masterEQ.value
  const eqLow = ctx.createBiquadFilter()
  eqLow.type = 'lowshelf'; eqLow.frequency.value = 120; eqLow.gain.value = low
  const eqMid = ctx.createBiquadFilter()
  eqMid.type = 'peaking'; eqMid.frequency.value = 1000; eqMid.Q.value = 1; eqMid.gain.value = mid
  const eqHigh = ctx.createBiquadFilter()
  eqHigh.type = 'highshelf'; eqHigh.frequency.value = 3500; eqHigh.gain.value = high
  src.connect(eqLow).connect(eqMid).connect(eqHigh).connect(ws).connect(ctx.destination)
  src.start(0)
  return await ctx.startRendering()
}

export async function offlineRenderRaw(
  url: string,
  styleId: string | undefined,
  durationSeconds: number,
  channelFilter: 'all' | 'melodic' | PlayerPart = 'all',
  onProgress?: (v: number) => void,
  format: AudioFormat = 'wav',
  audioClip?: { url: string; offsetSeconds: number } | null,
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
    const isMelodicSynth = styleId ? MELODIC_SYNTH_STYLES.has(styleId) : false

    // Mix settings (roadmap 6.5) — read once and passed through the closures below,
    // matching how useSynthPatches/useCustomInstruments/useDrumKitPatches are read.
    const mixSettings = useMixSettings()

    // Master loudness trim (roadmap 6.2), matching live playback (useMidiPlayer.ts's
    // setMasterTrimDb) — only for a full-mix export. A single-part stem isn't "the
    // mix" the trim was measured against, so it renders at its natural level.
    const trimDb = channelFilter === 'all'
      ? trimDbForStyle(styleId, fxFamilyFor({ isPad, isLofi, isSynth, isMelodicSynth }))
      : 0

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
        () => reject(new Error('Audio render timed out — try again, or export a shorter section')),
        timeoutMs,
      )
    })

    // Build the synth graph for a subset of parts. `wants(p)` picks which parts this
    // pass renders; `withLimiter` puts the master soft-clip limiter inline. The
    // parallel path renders each part on its OWN OfflineAudioContext WITHOUT the
    // limiter (Chromium bounces them on separate threads) and limits the summed mix
    // once afterwards; a single-part stem render keeps the limiter inline because its
    // output already IS the final mix. See the orchestration below.
    const buildGraph = async (context: Tone.OfflineContext, wants: (p: PlayerPart) => boolean, withLimiter: boolean) => {
      const dest = context.destination
      dest.volume.value = 0
      // Plain gain, not a Tone.Compressor — a DynamicsCompressorNode renders silence on
      // Linux packaged Electron (see getMasterCompressor in loader.ts), which would make
      // WAV exports silent there too. A WaveShaper soft-clip limiter after it catches
      // peaks so the exported WAV can't clip, matching live playback's master chain.
      let busOut: Tone.ToneAudioNode = dest
      if (withLimiter) {
        const limiter = makeMasterLimiter(context)
        limiter.connect(dest)
        busOut = limiter
        // Master EQ (roadmap 6.5), mirroring live playback's masterOut → EQ →
        // limiter chain (loader.ts). Only meaningful when this graph's output IS
        // the full mix — the multi-part parallel path (withLimiter=false) gets its
        // EQ once, on the summed buffer, in limitMix() below instead.
        if (channelFilter === 'all') {
          const { low, mid, high } = mixSettings.masterEQ.value
          const eqHigh = new Tone.Filter({ context, type: 'highshelf', frequency: 3500, gain: high }).connect(busOut)
          const eqMid = new Tone.Filter({ context, type: 'peaking', frequency: 1000, Q: 1, gain: mid }).connect(eqHigh)
          const eqLow = new Tone.Filter({ context, type: 'lowshelf', frequency: 120, gain: low }).connect(eqMid)
          busOut = eqLow
        }
      }
      const comp = new Tone.Gain({ context, gain: Tone.dbToGain(trimDb) }).connect(busOut)

      // Per-part output insert (roadmap 9.3), mirroring useMidiPlayer.ts's live-side
      // insert: every part's voice(s) connect here instead of straight to `comp`, so
      // a part's volume/pan applies uniformly regardless of which underlying voice it
      // uses. Unlike the live side this doesn't need to be persistent or reset — each
      // buildGraph() call is a fresh, one-shot offline render, and (per the orchestration
      // above) only ever carries ONE real part's audio, so a plain per-call cache suffices.
      //
      // Baked volume/pan curves (roadmap 9.3), keyed by part the same way
      // partHasNotes resolves channel -> part. No automation for a part -> falls
      // back to the `pan` argument callers already compute (panForChannel below),
      // so an unautomated render stays exactly what it was before this existed.
      const automationByPart = new Map<PlayerPart, { volume: AutomationBreakpoint[]; pan: AutomationBreakpoint[] }>()
      for (const t of midi.tracks) {
        if (t.notes.length === 0) continue
        const perc = t.instrument.percussion || (t.channel ?? 0) === 9
        const p = perc ? 'drums' : CHANNEL_PART[t.channel ?? 0] ?? 'chords'
        automationByPart.set(p, { volume: curveFromCC(t.controlChanges?.[7]), pan: curveFromCC(t.controlChanges?.[10]) })
      }

      const partInserts = new Map<PlayerPart, Tone.Gain>()
      const partInsert = (part: PlayerPart, pan: number): Tone.Gain => {
        const existing = partInserts.get(part)
        if (existing) return existing
        const automation = automationByPart.get(part)
        const initialPan = automation?.pan.length ? automation.pan[0].value * 2 - 1 : pan
        const initialVolume = automation?.volume.length ? automation.volume[0].value : 1
        // Per-part tone preset (roadmap 6.5), mirroring partInsert.ts's live insert:
        // gain → panner → toneLow → toneHigh → toneSat → comp. Baked in once at
        // construction (offline is one-shot, no live "setter" needed).
        const { lowShelfDb, highShelfDb, drive } = resolveToneValues(mixSettings.toneForPart(part))
        const toneSat = new Tone.WaveShaper({ context, mapping: x => saturationCurve(x, drive), length: 1024 }).connect(comp)
        const toneHigh = new Tone.Filter({ context, type: 'highshelf', frequency: 3500, gain: highShelfDb }).connect(toneSat)
        const toneLow = new Tone.Filter({ context, type: 'lowshelf', frequency: 120, gain: lowShelfDb }).connect(toneHigh)
        const panner = new Tone.Panner({ context, pan: initialPan }).connect(toneLow)
        const gain = new Tone.Gain({ context, gain: initialVolume }).connect(panner)
        partInserts.set(part, gain)
        scheduleOfflineAutomationTail(gain.gain, automation?.volume ?? [], v => v)
        scheduleOfflineAutomationTail(panner.pan, automation?.pan ?? [], v => v * 2 - 1)
        return gain
      }

      // Only needed so Transport-relative delay-time notation ('8n', '4n', …)
      // in the effects below resolves against the song's real tempo — no note
      // is actually scheduled through the Transport (see below). This is the
      // offline context's OWN transport, not the ambient one used by live
      // playback — mutating that would have audibly retempo'd anything
      // playing concurrently while this export ran.
      context.transport.bpm.value = bpm

      // ── Assigned voices: synth patches + custom instruments ──────────
      // Both render in export now, mirroring live playback's precedence:
      //   patch > custom instrument > built-in voice.
      // A patch is built from the SAME buildSynthFromPatch as live (threaded with THIS
      // OfflineContext); a custom instrument is materialized to blob URLs and loaded
      // into a LayeredSampler ON this context (awaited so buffers decode before render).
      const sp = useSynthPatches()
      const patchByPart: Partial<Record<PlayerPart, SynthPatch>> = {}
      for (const part of ['chords', 'bass', 'melody', 'arpeggio', 'pads', 'counter_melody'] as PlayerPart[]) {
        const p = sp.resolvePatchForPart(styleId, part)
        if (p) patchByPart[part] = p
      }

      // Static pan a part was written with (CC10) — so custom samplers sit where the
      // built-in voice would. Defined up here so the custom block can pan too.
      const panForChannel = (ch: number): number => {
        const track = midi.tracks.find(t => (t.channel ?? 0) === ch)
        const cc = track?.controlChanges?.[10]
        if (cc && cc.length) return Math.max(-1, Math.min(1, cc[cc.length - 1].value * 2 - 1))
        return 0
      }
      const PART_CHANNEL: Partial<Record<PlayerPart, number>> = { chords: 0, melody: 2, arpeggio: 3, pads: 4, counter_melody: 5 }

      // Custom instruments (Electron-only storage); skipped where a patch already wins.
      const customByPart: Partial<Record<PlayerPart, LayeredSampler>> = {}
      const customKit: KitSamplers = new Map()
      const ci = useCustomInstruments()
      if (ci.supported()) {
        await ci.ensureLoaded()
        for (const part of ['chords', 'bass', 'melody', 'arpeggio', 'pads', 'counter_melody'] as PlayerPart[]) {
          if (!wants(part) || patchByPart[part]) continue
          const r = resolvePartInstrument(ci.assignments.value, styleId, part, null)
          if (r.source !== 'custom') continue
          const manifest = await ci.materialize(r.id)
          if (!manifest || !manifest.layers.length) continue
          const ls = new LayeredSampler({ baseUrl: '', manifest, volume: -6, context })
          const out = partInsert(part, part === 'bass' ? 0 : panForChannel(PART_CHANNEL[part] ?? 0))
          ls.connect(out)
          await ls.loaded
          customByPart[part] = ls
        }
        if (wants('drums')) {
          const drumChoice = resolvePartInstrument(ci.assignments.value, styleId, 'drums', null)
          if (drumChoice.source === 'custom') {
            const kit = await ci.materializeKit(drumChoice.id)
            for (const [pitch, m] of Object.entries(kit ?? {})) {
              if (!m.layers.length) continue
              const ls = new LayeredSampler({ baseUrl: '', manifest: m, volume: -4, context })
              ls.connect(partInsert('drums', 0))
              await ls.loaded
              customKit.set(Number(pitch), ls)
            }
          }
        }
      }

      // ── Drum kit ─────────────────────────────────────────────────────
      // Synthesized engine + the kit's own "sample base" (Drum Designer) blended in,
      // then any style-assigned custom kit piece (hybrid) still wins outright — routed
      // to the offline compressor so the export matches what the user auditions.
      let drumKit = null
      if (wants('drums')) {
        const resolvedDrumPatch = useDrumKitPatches().resolveKitForStyle(styleId)
        const synthDrumKit = makeSynthKit(resolvedDrumPatch, partInsert('drums', 0), context)
        const patchSamplers = await materializeSampleLayer(
          ci, resolvedDrumPatch.sampleKitId, partInsert('drums', 0), context,
        )
        drumKit = makeHybridKit(makeBlendedKit(synthDrumKit, patchSamplers, resolvedDrumPatch.sampleBlend), customKit)
      }

      // ── Bass ─────────────────────────────────────────────────────────
      // Patch > custom instrument > built-in synth bass.
      let bassSynth: Tone.MonoSynth | Tone.PolySynth | LayeredSampler | null = null
      if (wants('bass')) {
        bassSynth = (patchByPart.bass ? buildSynthFromPatch(patchByPart.bass, [], partInsert('bass', 0), context) : null)
          ?? customByPart.bass
          ?? new Tone.MonoSynth({
          context,
          oscillator: { type: 'sawtooth' },
          filter: { Q: 2, type: 'lowpass', rolloff: -24 },
          envelope: { attack: 0.01, decay: 0.1, sustain: 0.9, release: 0.5 },
          filterEnvelope: { attack: 0.06, decay: 0.2, sustain: 0.5, release: 0.5, baseFrequency: 200, octaves: 2.6 },
          volume: -3,
        }).connect(partInsert('bass', 0))
      }

      // ── Melodic synths ───────────────────────────────────────────────
      // Mirror live playback: chords / melody / arpeggio each get a distinct
      // voice, connected through that part's insert (panned from CC10 — set by
      // the caller, mkPartVoice below — so the export matches the preview).
      const mkVoice = (variant: 'chords' | 'lead' | 'arp' | 'pads' | 'strings', out: Tone.ToneAudioNode): Tone.PolySynth => {
        if (variant === 'arp') {
          const delay = new Tone.FeedbackDelay({ context, delayTime: '8n.', feedback: 0.24, wet: 0.16 }).connect(out)
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
          const delay = new Tone.FeedbackDelay({ context, delayTime: '4n', feedback: 0.4, wet: 0.3 }).connect(out)
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
          const lp = new Tone.Filter({ context, frequency: 2400, type: 'lowpass' }).connect(out)
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
          const delay = new Tone.FeedbackDelay({ context, delayTime: '8n.', feedback: 0.22, wet: soft ? 0.22 : 0.14 }).connect(out)
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
          const delay = new Tone.FeedbackDelay({ context, delayTime: '4n', feedback: 0.38, wet: 0.28 }).connect(out)
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
          const lp = new Tone.Filter({ context, frequency: 5200, type: 'lowpass' }).connect(out)
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
            const lp = new Tone.Filter({ context, frequency: 2600, type: 'lowpass' }).connect(out)
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
          const delay = new Tone.PingPongDelay({ context, delayTime: '8n', feedback: 0.18, wet: 0.1 }).connect(out)
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
        }).connect(out)
      }

      type MelodicVoice = Tone.PolySynth | LayeredSampler
      let chordsSynth: MelodicVoice | null = null
      let leadSynth: MelodicVoice | null = null
      let arpSynth: MelodicVoice | null = null
      let padsSynth: MelodicVoice | null = null
      let stringsSynth: MelodicVoice | null = null
      const hasTrackOn = (ch: number) =>
        midi.tracks.some(t => (t.channel ?? 0) === ch && t.notes.length > 0)
      // Precedence: patch > custom instrument > built-in variant. Patch/built-in connect
      // through this part's insert; the custom sampler was already connected through
      // its own insert when it was materialized above.
      const mkPartVoice = (part: PlayerPart, variant: 'chords' | 'lead' | 'arp' | 'pads' | 'strings', ch: number): MelodicVoice => {
        const p = patchByPart[part]
        if (p) {
          return buildSynthFromPatch(p, [], partInsert(part, panForChannel(ch)), context) as Tone.PolySynth
        }
        return customByPart[part] ?? mkVoice(variant, partInsert(part, panForChannel(ch)))
      }
      // Only built when wanted AND the file actually carries the part — keeps
      // the offline graph light for single-stem renders.
      if (wants('chords'))   chordsSynth = mkPartVoice('chords', 'chords', 0)
      if (wants('melody'))   leadSynth   = mkPartVoice('melody', 'lead', 2)
      if (wants('arpeggio')) arpSynth    = mkPartVoice('arpeggio', 'arp', 3)
      if (wants('pads') && hasTrackOn(4))           padsSynth    = mkPartVoice('pads', 'pads', 4)
      if (wants('counter_melody') && hasTrackOn(5)) stringsSynth = mkPartVoice('counter_melody', 'strings', 5)

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
    }

    // The individual parts this render covers: the wanted universe intersected with
    // the parts the file actually carries. Each renders on its own OfflineAudioContext
    // so Chromium can bounce them on separate threads (measured ~2.5× faster on 8
    // cores); the per-part graphs never interact, so the summed mix is the same signal
    // the single-pass graph fed its limiter. A lone part (stem export) has nothing to
    // parallelise, so it renders inline with the limiter — its output IS the mix.
    const present = PLAYER_PARTS.filter(p => wantsPart(p) && partHasNotes(midi, p))

    // If the timeout wins a race, the render keeps going in the background (an
    // OfflineAudioContext can't be cancelled) — the `.catch(() => {})` on each promise
    // swallows its eventual settlement so a late rejection isn't an unhandled promise.
    let finalBuffer: AudioBuffer
    try {
      if (present.length <= 1) {
        const single = renderOfflineFast(c => buildGraph(c, wantsPart, true), totalDuration, 2)
        single.catch(() => {})
        const toneBuffer = await Promise.race([single, timeout])
        const ab = toneBuffer.get()
        if (!ab) throw new Error('Offline render returned empty buffer')
        finalBuffer = ab
      } else {
        // Render every part in parallel (no limiter); progress advances as each lands.
        let done = 0
        const partRenders = present.map(p =>
          renderOfflineFast(c => buildGraph(c, q => q === p, false), totalDuration, 2)
            .then(buf => {
              done += 1
              onProgress?.(0.08 + 0.8 * (done / present.length))
              return buf
            }),
        )
        partRenders.forEach(pr => pr.catch(() => {}))
        const dry = await Promise.race([Promise.all(partRenders), timeout])
        const buffers = dry.map(b => b.get()).filter((b): b is AudioBuffer => !!b)
        if (buffers.length === 0) throw new Error('Offline render returned empty buffer')
        onProgress?.(0.9)

        // A recorded audio clip (roadmap 9.4) mixes in as one more buffer, placed
        // at its bar-aligned offset — only for the full mix, never a single-part
        // stem export (a clip isn't a "part"). Best-effort: a failed fetch/decode
        // just exports without it rather than failing the whole render.
        let mixInputs: Array<Pick<AudioBuffer, 'length' | 'sampleRate' | 'numberOfChannels' | 'getChannelData'>> = buffers
        if (audioClip && channelFilter === 'all') {
          try {
            const clipBytes = await fetch(audioClip.url).then(r => r.arrayBuffer())
            const decodeCtx = new OfflineAudioContext(2, 1, buffers[0].sampleRate)
            const decoded = await decodeCtx.decodeAudioData(clipBytes)
            const totalLength = Math.max(...buffers.map(b => b.length))
            mixInputs = [...buffers, placeClipInMix(decoded, audioClip.offsetSeconds, totalLength)]
          } catch (e) {
            console.warn('[export] audio clip failed to mix into the render — continuing without it', e)
          }
        }
        // Sum the parts (+ clip, if any) and apply the master limiter once, on the full mix.
        finalBuffer = await limitMix(mixInputs)
      }
    } finally {
      clearInterval(progressTimer)
      if (timeoutHandle !== null) clearTimeout(timeoutHandle)
    }

    onProgress?.(0.92)
    // WAV is instant; MP3/OGG lazy-load the WASM encoder here (only on demand).
    const blob = await encodeAudio(finalBuffer, format)
    onProgress?.(1)
    return blob
  } finally {
    isRendering.value = false
  }
}
