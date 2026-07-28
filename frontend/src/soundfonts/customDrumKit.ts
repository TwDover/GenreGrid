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
import type { SynthKit } from './synthDrums'
import type { LayeredSampler } from './layeredSampler'
import { KIT_ROOT } from './customInstruments'

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
