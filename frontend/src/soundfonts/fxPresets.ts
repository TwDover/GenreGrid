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
import type { Unit } from 'tone'

// ── Per-style master FX presets ──────────────────────────────────────────────
// The shared melodic bus carries one chorus + feedback-delay, and a shared reverb
// sits behind it (see loader.ts). Those used to be fixed for every style, so an
// ambient wash and a funk comp got identical space. These presets retune that
// shared chain per style FAMILY — the same families useMidiPlayer already derives
// for voice selection — so each genre sits in its own room. loader.applyMelodicFx-
// Preset() sets these live; only a changed reverb decay costs an IR regenerate.

export interface MelodicFxPreset {
  chorus: { frequency: number; depth: number; wet: number }
  delay: { delayTime: Unit.Time; feedback: number; wet: number }
  reverb: { decay: number; wet: number }
}

export type FxFamily = 'default' | 'synth' | 'melodicSynth' | 'pad' | 'lofi'

export const MELODIC_FX_PRESETS: Record<FxFamily, MelodicFxPreset> = {
  // Acoustic / pop / hip-hop with sampled voices — tasteful, present, not washy.
  default: {
    chorus: { frequency: 1.5, depth: 0.3, wet: 0.18 },
    delay:  { delayTime: '8n.', feedback: 0.22, wet: 0.12 },
    reverb: { decay: 1.6, wet: 0.22 },
  },
  // Electronic — more movement and rhythmic delay to fill the grid.
  synth: {
    chorus: { frequency: 1.2, depth: 0.5, wet: 0.28 },
    delay:  { delayTime: '8n', feedback: 0.30, wet: 0.18 },
    reverb: { decay: 1.4, wet: 0.18 },
  },
  // Trap/drill leads — tight and dry so the lead cuts; reverb stays short.
  melodicSynth: {
    chorus: { frequency: 1.0, depth: 0.2, wet: 0.10 },
    delay:  { delayTime: '8n', feedback: 0.18, wet: 0.10 },
    reverb: { decay: 1.1, wet: 0.14 },
  },
  // Ambient / cinematic / cloud — long lush tail, wide chorus, generous delay.
  pad: {
    chorus: { frequency: 0.7, depth: 0.6, wet: 0.35 },
    delay:  { delayTime: '4n', feedback: 0.40, wet: 0.28 },
    reverb: { decay: 3.2, wet: 0.38 },
  },
  // Lo-fi — slow wobbly chorus, gentle short room, restrained delay.
  lofi: {
    chorus: { frequency: 0.5, depth: 0.7, wet: 0.30 },
    delay:  { delayTime: '8n.', feedback: 0.25, wet: 0.14 },
    reverb: { decay: 1.2, wet: 0.20 },
  },
}

// ── Loudness normalization ───────────────────────────────────────────────────
// A per-family trim (dB) on the pre-limiter master so perceived loudness doesn't
// jump when you switch styles. Dense electronic mixes run hot and get pulled down;
// sparse/soft families sit near unity. These are calibrated starting points (a true
// per-style LUFS target would need offline measurement) — safe to hand-tune by ear.
// Applied via loader.setMasterTrimDb() when a style starts.
export const MASTER_TRIM_DB: Record<FxFamily, number> = {
  default: 0,        // sampled acoustic/pop — the reference level
  synth: -2.5,       // four-on-the-floor + sidechain runs loud
  melodicSynth: -1.5,
  pad: 1.0,          // sustained washes read quieter than transient material
  lofi: -0.5,
}

/** Resolve the FX family from the booleans useMidiPlayer already computes for a
 *  style. Order matters: pad and lo-fi override the synth buckets. */
export function fxFamilyFor(flags: {
  isPad: boolean
  isLofi: boolean
  isSynth: boolean
  isMelodicSynth: boolean
}): FxFamily {
  if (flags.isPad) return 'pad'
  if (flags.isLofi) return 'lofi'
  if (flags.isMelodicSynth) return 'melodicSynth'
  if (flags.isSynth) return 'synth'
  return 'default'
}
