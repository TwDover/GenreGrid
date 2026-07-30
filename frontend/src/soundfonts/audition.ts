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
import { getDrumBus, getMelodicBus } from './loader'
import { makeSynthKit, type SynthKit } from './synthDrums'
import { drumCharacterForStyle } from './drums'
import { KIT_ROOT } from './customInstruments'
import { buildSynthFromPatch, type SynthPatch } from './synthPatch'

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

// One synth kit per drum character, reused across clicks. Auditioning an empty slot
// should sound like the fallback the track will actually use, which depends on the
// style's character — so it is keyed by character, not built once.
const synthByCharacter = new Map<string, SynthKit>()

/** Play the synthesized version of a piece — what an unfilled slot falls back to in
 *  a track under `styleId`. */
export async function auditionSynthPiece(pitch: number, styleId?: string): Promise<void> {
  await Tone.start()
  const character = drumCharacterForStyle(styleId)
  let kit = synthByCharacter.get(character)
  if (!kit) {
    kit = makeSynthKit(character)
    synthByCharacter.set(character, kit)
  }
  kit.trigger(pitch, 0.9, Tone.now())
}

/** Free every audition synth kit. Call when the editor closes so its nodes don't
 *  linger in the audio graph. */
export function disposeAudition(): void {
  for (const kit of synthByCharacter.values()) {
    for (const node of kit.nodes) node.dispose()
  }
  synthByCharacter.clear()
}

// ── Live audition for the synth designer ─────────────────────────────────────
// The designer needs to hear the patch it's editing on a keyboard. We keep ONE
// throwaway voice built from the current patch (via the same buildSynthFromPatch a
// track uses, so it sounds exactly like playback), rebuilt only when the patch
// actually changes — dragging a slider then hitting a key rebuilds once, not on
// every input event. The preview routes through the shared melodic bus so its
// chorus/delay match a real render.

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
    previewVoice = buildSynthFromPatch(patch, previewNodes, getMelodicBus())
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
