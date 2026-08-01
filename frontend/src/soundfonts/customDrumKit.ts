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
import type * as Tone from 'tone'
import type { SynthKit } from './synthDrums'
import { LayeredSampler } from './layeredSampler'
import { KIT_ROOT } from './customInstruments'
import type { useCustomInstruments } from '../composables/useCustomInstruments'

// ── Hybrid drum kit: user samples over the synth kit ─────────────────────────
// A user kit is almost never complete — someone drops a kick and a snare they like
// and leaves the rest. Rather than making them fill twelve slots before they hear
// anything, an unfilled piece simply plays the synthesized version, so a two-file
// kit is useful the moment it is imported.
//
// Each filled piece is its own LayeredSampler holding a single zone at KIT_ROOT.
// One zone per piece is the whole point: a sampler with several zones would
// pitch-shift between them, and a kick stretched up to cover a missing ride is
// not a drum sound anyone wants.

/** Which pitch each sampler answers to. Keys are GM percussion pitches. */
export type KitSamplers = Map<number, LayeredSampler>

/**
 * Wrap a synth kit so mapped pitches play the user's samples and everything else
 * falls through untouched. The result is a drop-in `SynthKit`, so callers schedule
 * drums exactly as before.
 *
 * `nodes` deliberately carries only the synth's nodes: the samplers have their own
 * lifetime (they are cached per instrument and disposed with the play session), and
 * disposing them here would tear down a cached instrument mid-use.
 */
export function makeHybridKit(synth: SynthKit, samplers: KitSamplers): SynthKit {
  if (samplers.size === 0) return synth
  return {
    trigger(pitch: number, velocity: number, time: number) {
      const sampler = samplers.get(pitch)
      if (sampler) sampler.triggerAttack(KIT_ROOT, time, velocity)
      else synth.trigger(pitch, velocity, time)
    },
    nodes: synth.nodes,
  }
}

// ── Blended kit: a sample as a base UNDER the synth, not instead of it ────────
// makeHybridKit above is all-or-nothing per piece (a mapped sample wins outright —
// the right behavior for a deliberately-assigned style kit). The Drum Designer's
// "sample base" is different: the user is shaping the SYNTH and wants a real sample
// blended in for realism, so a covered piece plays BOTH, mixed via `blend`.

/** Blend `synth` with `samplers` at a fixed ratio: any piece `samplers` covers plays
 *  BOTH the synth and the sample together, each scaled by `blend` through velocity
 *  (0 = pure synth, 1 = pure sample) — reusing velocity as the mix control needs no
 *  new gain-node wiring, and is the same lever the engine's velocity→brightness
 *  behavior already leans on. A piece `samplers` doesn't cover is untouched. */
export function makeBlendedKit(synth: SynthKit, samplers: KitSamplers, blend: number): SynthKit {
  if (samplers.size === 0 || blend <= 0) return synth
  return {
    trigger(pitch: number, velocity: number, time: number) {
      const sampler = samplers.get(pitch)
      if (!sampler) { synth.trigger(pitch, velocity, time); return }
      if (blend < 1) synth.trigger(pitch, velocity * (1 - blend), time)
      sampler.triggerAttack(KIT_ROOT, time, velocity * blend)
    },
    nodes: synth.nodes,   // samplers have their own lifetime — same rationale as makeHybridKit
  }
}

/** Turn a stored drum sample kit (a `CustomInstrument` id) into one `LayeredSampler`
 *  per mapped piece, connected to `out` — the same materialize-then-build-a-sampler-
 *  per-pitch shape `useMidiPlayer.ts`/`useOfflineRender.ts` already do inline for the
 *  style-assigned sample kit, factored out so the Drum Designer's patch-level sample
 *  base can reuse it. Resolves to an empty map for an unset/missing/unsupported id —
 *  callers get a graceful "no sample layer" rather than an error. */
export async function materializeSampleLayer(
  ci: ReturnType<typeof useCustomInstruments>,
  sampleKitId: string | undefined,
  out: Tone.ToneAudioNode,
  context?: Tone.BaseContext,
): Promise<KitSamplers> {
  const samplers: KitSamplers = new Map()
  if (!sampleKitId || !ci.supported()) return samplers
  const kit = await ci.materializeKit(sampleKitId)
  if (!kit) return samplers
  await Promise.all(Object.entries(kit).map(async ([pitch, manifest]) => {
    if (!manifest.layers.length) return
    const ls = new LayeredSampler({ baseUrl: '', manifest, volume: -4, context })
    ls.connect(out)
    await ls.loaded
    samplers.set(Number(pitch), ls)
  }))
  return samplers
}
