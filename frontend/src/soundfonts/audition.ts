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
import * as Tone from 'tone'
import { LayeredSampler, type LayeredSamplerManifest } from './layeredSampler'
import { getDrumBus, getMasterCompressor } from './loader'
import { makeSynthKit, type SynthKit, type DrumKitPatch } from './synthDrums'
import { KIT_ROOT } from './customInstruments'
import { makeBlendedKit, materializeSampleLayer, type KitSamplers } from './customDrumKit'
import { buildSynthFromPatch, type SynthPatch } from './synthPatch'
import { useDrumKitPatches } from '../composables/useDrumKitPatches'
import { useCustomInstruments } from '../composables/useCustomInstruments'

// ── One-shot audition for the kit editor ─────────────────────────────────────
// The kit editor is otherwise silent, so a file landing on the wrong drum only
// surfaces on real playback. These play a single piece on demand — a filled slot
// plays the user's sample, an empty one plays the synth fallback it would use in a
// track — so the mapping can be checked by ear right where it's edited.
//
// Auditioning is a preview and never touches the play session's cached instruments:
// it builds its own throwaway sampler and keeps its own synth kit.

// How long the longest plausible one-shot (a crash) needs to ring before its
// sampler can be freed. A short audition sound is disposed well within this.
const RING_OUT_MS = 5000

/** Play a single kit piece (a single-zone manifest) once, at a strong velocity so
 *  the top layer is heard. Disposes the throwaway sampler after it rings out. */
export async function auditionPiece(manifest: LayeredSamplerManifest): Promise<void> {
  await Tone.start()
  const sampler = new LayeredSampler({ baseUrl: '', manifest, volume: -4 })
  await sampler.loaded
  sampler.connect(getDrumBus())
  sampler.triggerAttack(KIT_ROOT, Tone.now(), 0.95)
  setTimeout(() => sampler.dispose(), RING_OUT_MS)
}

// One synth kit per style, reused across clicks. Auditioning an empty slot should
// sound like the fallback the track will actually use, which depends on the
// style's resolved kit patch (built-in character, or a user assignment) — so it
// is keyed by style, not built once.
const synthByStyle = new Map<string, SynthKit>()

/** Play the synthesized version of a piece — what an unfilled slot falls back to in
 *  a track under `styleId`. */
export async function auditionSynthPiece(pitch: number, styleId?: string): Promise<void> {
  await Tone.start()
  const key = styleId ?? ''
  let kit = synthByStyle.get(key)
  if (!kit) {
    kit = makeSynthKit(useDrumKitPatches().resolveKitForStyle(styleId))
    synthByStyle.set(key, kit)
  }
  kit.trigger(pitch, 0.9, Tone.now())
}

/** Free every audition synth kit. Call when the editor closes so its nodes don't
 *  linger in the audio graph. */
export function disposeAudition(): void {
  for (const kit of synthByStyle.values()) {
    for (const node of kit.nodes) node.dispose()
  }
  synthByStyle.clear()
}

// ── Live audition for the synth designer ─────────────────────────────────────
// The designer needs to hear the patch it's editing on a keyboard. We keep ONE
// throwaway voice built from the current patch (via the same buildSynthFromPatch a
// track uses), rebuilt only when the patch actually changes — dragging a slider then
// hitting a key rebuilds once, not on every input event.
//
// The preview routes DRY, straight to the master compressor — NOT through the shared
// melodic bus. That bus adds a chorus + a dotted-eighth feedback delay meant for
// melodic style voices; on a bass patch it reads as an unwanted rhythmic echo. Going
// dry lets the patch be judged on its own sound (its own FX chain still plays); a
// bass patch already renders dry in a track (it plays through the bass bus).

let previewNodes: Tone.ToneAudioNode[] = []
let previewVoice: Tone.PolySynth | Tone.MonoSynth | null = null
let previewSig = ''

/** Play `note` on the patch under design, rebuilding the preview voice first if the
 *  patch changed since the last note. `note` is a scientific-pitch name (e.g. "C4"). */
export async function auditionPatchNote(patch: SynthPatch, note: string, velocity = 0.85): Promise<void> {
  await Tone.start()
  const sig = JSON.stringify(patch)
  if (!previewVoice || sig !== previewSig) {
    disposeSynthPreview()
    previewNodes = []
    previewVoice = buildSynthFromPatch(patch, previewNodes, getMasterCompressor())
    previewSig = sig
  }
  previewVoice.triggerAttackRelease(note, '8n', Tone.now(), velocity)
}

/** Free the designer's preview voice. Call when the designer closes so its nodes
 *  don't linger in the audio graph. */
export function disposeSynthPreview(): void {
  for (const node of previewNodes) node.dispose()
  previewNodes = []
  previewVoice = null
  previewSig = ''
}

// ── Live audition for the drum designer ───────────────────────────────────────
// Same rebuild-only-on-change approach as the synth preview above, but a SynthKit
// instead of a single voice — one kit is built from the patch under design and
// reused across pad hits until the patch changes.

let drumPreviewKit: SynthKit | null = null
let drumPreviewSig = ''

// The patch's sample-base layer (see DrumKitPatch.sampleKitId) materializes over IPC —
// too slow to await from the groove clock's sync callback. Cached separately from the
// synth-rebuild cache above (keyed by sampleKitId, not the whole patch signature) so
// dragging an unrelated slider like kick decay never re-fetches/re-materializes it.
const sampleLayerCache = new Map<string, KitSamplers>()
const sampleLayerLoading = new Set<string>()

/** The sample layer for `sampleKitId`, or an empty map if unset/not loaded yet. A
 *  cache miss kicks off materializing it in the background and returns empty
 *  immediately — the kit plays pure synth until it resolves, then the next hit/tick
 *  picks up the blend (forced via invalidating the synth-rebuild cache below), the
 *  same graceful-degrade approach makeHybridKit already uses for unfilled pieces. */
function ensurePatchSamplers(sampleKitId: string | undefined): KitSamplers {
  if (!sampleKitId) return new Map()
  const cached = sampleLayerCache.get(sampleKitId)
  if (cached) return cached
  if (!sampleLayerLoading.has(sampleKitId)) {
    sampleLayerLoading.add(sampleKitId)
    void materializeSampleLayer(useCustomInstruments(), sampleKitId, getMasterCompressor())
      .then((samplers) => {
        sampleLayerCache.set(sampleKitId, samplers)
        sampleLayerLoading.delete(sampleKitId)
        drumPreviewSig = ''   // force the next call to rebuild with the sample layer included
      })
  }
  return new Map()
}

/** Dispose just the synth voice (not the sample-layer cache — that's keyed and
 *  reused independently, see `ensurePatchSamplers`). Used on every patch-signature
 *  change; `disposeDrumPreview` below (designer close) additionally clears the cache. */
function disposeDrumSynth(): void {
  if (drumPreviewKit) for (const node of drumPreviewKit.nodes) node.dispose()
  drumPreviewKit = null
  drumPreviewSig = ''
}

/** The kit currently under design, rebuilding it first if the patch changed since the
 *  last call. Shared by pad hits and the groove loop below so both always hear the
 *  same live-edited kit through one cache. */
function getDrumPreviewKit(patch: DrumKitPatch): SynthKit {
  const sig = JSON.stringify(patch)
  if (!drumPreviewKit || sig !== drumPreviewSig) {
    disposeDrumSynth()
    const base = makeSynthKit(patch, getMasterCompressor())
    drumPreviewKit = makeBlendedKit(base, ensurePatchSamplers(patch.sampleKitId), patch.sampleBlend)
    drumPreviewSig = sig
  }
  return drumPreviewKit
}

/** Hit `pitch` (a GM percussion note) on the kit patch under design, rebuilding the
 *  preview kit first if the patch changed since the last hit. */
export async function auditionDrumHit(patch: DrumKitPatch, pitch: number, velocity = 0.9): Promise<void> {
  await Tone.start()
  getDrumPreviewKit(patch).trigger(pitch, velocity, Tone.now())
}

/** Free the drum designer's preview kit and its cached sample layers. Call when the
 *  designer closes so nothing lingers in the audio graph. */
export function disposeDrumPreview(): void {
  disposeDrumSynth()
  for (const samplers of sampleLayerCache.values()) for (const s of samplers.values()) s.dispose()
  sampleLayerCache.clear()
  sampleLayerLoading.clear()
}

// ── Demo groove loop for the drum designer ─────────────────────────────────────
// Hearing one piece at a time on the pads doesn't tell you how a kit FEELS in a beat
// — punch, how the kick/snare sit together, whether the hats hold up busy. This plays
// a short canned pattern on repeat through the SAME live preview kit above, so slider
// edits and preset swaps are heard in context, not just in isolation.
//
// Deliberately NOT on Tone.Transport: useMidiPlayer.ts owns that as the single shared
// clock for real playback (bpm/start/stop/loop state), and there's no way to run an
// independent loop on it without fighting over that state if a track happens to be
// loaded. Tone.Clock is the Tone.js primitive for exactly this — a sample-accurate,
// Transport-independent repeating callback.

const STEPS_PER_BAR = 16
const GROOVE_BARS = 2
const GROOVE_STEPS = STEPS_PER_BAR * GROOVE_BARS

const GROOVE_KICK = 36, GROOVE_SNARE = 38, GROOVE_CLOSED_HAT = 42, GROOVE_OPEN_HAT = 46, GROOVE_CRASH = 49, GROOVE_TOM = 45

/** A 2-bar demo pattern (16th-note steps) exercising every voice the designer edits:
 *  kick on 1 & 3, snare on 2 & 4, 8th-note closed hats with an open-hat pickup before
 *  beat 3, a crash on the downbeat, and a short tom fill closing bar 2. */
const GROOVE_PATTERN: { step: number; pitch: number; velocity: number }[] = [
  { step: 0, pitch: GROOVE_CRASH, velocity: 0.9 }, { step: 0, pitch: GROOVE_KICK, velocity: 1.0 },
  { step: 4, pitch: GROOVE_SNARE, velocity: 0.95 },
  { step: 8, pitch: GROOVE_KICK, velocity: 0.9 },
  { step: 12, pitch: GROOVE_SNARE, velocity: 1.0 },
  { step: 16, pitch: GROOVE_KICK, velocity: 1.0 },
  { step: 20, pitch: GROOVE_SNARE, velocity: 0.95 },
  { step: 24, pitch: GROOVE_KICK, velocity: 0.85 }, { step: 24, pitch: GROOVE_KICK, velocity: 0.7 },
  { step: 28, pitch: GROOVE_SNARE, velocity: 1.0 },
  { step: 30, pitch: GROOVE_TOM, velocity: 0.8 },
  { step: 31, pitch: GROOVE_TOM, velocity: 0.9 },
  ...Array.from({ length: GROOVE_STEPS / 2 }, (_, i) => ({
    step: i * 2, pitch: i % 4 === 3 ? GROOVE_OPEN_HAT : GROOVE_CLOSED_HAT, velocity: i % 2 === 0 ? 0.8 : 0.6,
  })),
]

let grooveClock: Tone.Clock | null = null
let grooveStep = 0
let grooveGetPatch: (() => DrumKitPatch) | null = null

/** Start (or restart) the demo groove, reading the kit to play fresh on every step via
 *  `getPatch` — so live slider edits and preset/prev-next swaps are heard on the very
 *  next step, not just when the loop was (re)started. */
export async function startDrumGroove(getPatch: () => DrumKitPatch, bpm = 96): Promise<void> {
  await Tone.start()
  stopDrumGroove()
  grooveGetPatch = getPatch
  grooveStep = 0
  const stepSeconds = 60 / bpm / 4   // a 16th note at `bpm`
  grooveClock = new Tone.Clock((time) => {
    const s = grooveStep % GROOVE_STEPS
    const patch = grooveGetPatch!()
    for (const hit of GROOVE_PATTERN) {
      if (hit.step === s) getDrumPreviewKit(patch).trigger(hit.pitch, hit.velocity, time)
    }
    grooveStep++
  }, 1 / stepSeconds)
  grooveClock.start()
}

export function stopDrumGroove(): void {
  grooveClock?.stop()
  grooveClock?.dispose()
  grooveClock = null
  grooveGetPatch = null
}

export function isDrumGrooveRunning(): boolean {
  return grooveClock !== null
}
