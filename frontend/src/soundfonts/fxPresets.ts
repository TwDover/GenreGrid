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
// A per-family trim (dB) on the pre-limiter master — kept as the fallback for any
// style not covered by STYLE_TRIM_DB below (e.g. a brand-new style before its next
// measurement sweep). Superseded as the PRIMARY source by STYLE_TRIM_DB for every
// style currently shipped (roadmap 6.2 — see there for why per-family wasn't
// precise enough).
export const MASTER_TRIM_DB: Record<FxFamily, number> = {
  default: 0,        // sampled acoustic/pop — the reference level
  synth: -2.5,       // four-on-the-floor + sidechain runs loud
  melodicSynth: -1.5,
  pad: 1.0,          // sustained washes read quieter than transient material
  lofi: -0.5,
}

// True per-style trim (dB) on the pre-limiter master, applied to BOTH live
// playback (loader.setMasterTrimDb, in useMidiPlayer.ts) and a full-mix offline
// export (useOfflineRender.ts) — before this, offline export applied NO trim at
// all (a real live/export loudness mismatch, the same shape of bug 9.3 found and
// fixed for pan). Measured by rendering each style's real offline mix (samplers,
// synths, per-style FX, the limiter — the actual signal a listener hears) and
// computing ITU-R BS.1770-4 gated integrated loudness against a −14 LUFS target:
// trim = −14 − measured. See .claude/skills/run-genregrid/scenarios/measure-lufs.mjs
// (an 8-bar loop per style, seed 42, default complexity/variation) — re-run it and
// update this table if a style's generation defaults change enough to matter.
// Never applied to a single-part stem export — a stem isn't "the mix".
export const STYLE_TRIM_DB: Record<string, number> = {
  afrobeats: -0.6,
  afropop: -0.2,
  ambient: 0.6,
  baile_funk: 0.2,
  boom_bap: 0.2,
  bossa_nova: -1.6,
  cinematic: 0.5,
  cloud_rap: -1.9,
  cumbia: -0.1,
  dancehall: 0.4,
  dark_ambient: -1.9,
  dark_trap: -2.1,
  doom_metal: 1.9,
  drill: -0.8,
  drum_and_bass: 1.0,
  epic_orchestral: 0.3,
  funk: 0.5,
  future_bass: 0.9,
  grime: 0.3,
  hip_hop: 0.7,
  house: 0.9,
  hyperpop: -0.6,
  jazz: -0.6,
  jersey_club: 0.9,
  latin_jazz: -1.6,
  lofi: -0.9,
  metal: -0.8,
  rnb: 0.3,
  reggaeton: 0.2,
  rock: 1.3,
  samba: -0.7,
  soul: -0.8,
  synthwave: 1.2,
  techno: 1.1,
  trap_soul: -2.6,
}

/** Resolve the master trim (dB) for a style: the measured per-style value if
 *  we have one, else the family-level fallback. */
export function trimDbForStyle(styleId: string | undefined, fxFamily: FxFamily): number {
  if (styleId && styleId in STYLE_TRIM_DB) return STYLE_TRIM_DB[styleId]
  return MASTER_TRIM_DB[fxFamily]
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
