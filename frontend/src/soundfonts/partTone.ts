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

// ── Per-part tone presets (roadmap 6.5) ──────────────────────────────────────
// A couple of tasteful, fixed-shape presets rather than a per-band console: each
// preset is a tuned {low-shelf, high-shelf, drive} triple that scales linearly with
// a single 0–1 "amount" knob. Applied at the existing per-part insert (partInsert.ts
// live, useOfflineRender.ts's local mirror), downstream of every voice type.

export type TonePresetId = 'neutral' | 'warm' | 'bright' | 'saturated'

export interface TonePreset {
  label: string
  lowShelfDb: number   // @120Hz, at amount = 1
  highShelfDb: number  // @3.5kHz, at amount = 1
  drive: number         // saturationCurve drive, at amount = 1 (0 = no drive)
}

export const TONE_PRESETS: Record<TonePresetId, TonePreset> = {
  neutral:   { label: 'Neutral',   lowShelfDb: 0,    highShelfDb: 0,    drive: 0 },
  warm:      { label: 'Warm',      lowShelfDb: 3,    highShelfDb: -2,   drive: 0 },
  bright:    { label: 'Bright',    lowShelfDb: -1.5, highShelfDb: 3,    drive: 0 },
  saturated: { label: 'Saturated', lowShelfDb: 0,    highShelfDb: 0,    drive: 2.5 },
}

export const TONE_PRESET_IDS: readonly TonePresetId[] = ['neutral', 'warm', 'bright', 'saturated']

export interface PartTone { preset: TonePresetId; amount: number } // amount: 0–1

export const DEFAULT_PART_TONE: PartTone = { preset: 'neutral', amount: 1 }

/** Resolve a preset + amount into the concrete {low, high, drive} values to apply
 *  to a part's tone-insert nodes. Amount scales the preset's tuned values linearly;
 *  'neutral' is unaffected (0 either way). */
export function resolveToneValues(tone: PartTone): { lowShelfDb: number; highShelfDb: number; drive: number } {
  const preset = TONE_PRESETS[tone.preset]
  const amount = Math.max(0, Math.min(1, tone.amount))
  return {
    lowShelfDb: preset.lowShelfDb * amount,
    highShelfDb: preset.highShelfDb * amount,
    drive: preset.drive * amount,
  }
}

// Light saturation transfer curve: tanh soft drive, normalized so it's unity gain
// at x=0 slope and transparent (identity) at drive=0. `x` is an AudioRange [-1, 1]
// sample value. Exported for unit testing (the WaveShaper node itself needs an
// AudioContext) — same pattern as loader.ts's softClipCurve.
export function saturationCurve(x: number, drive: number): number {
  if (drive <= 0) return x
  const k = 1 + drive
  return Math.tanh(x * k) / Math.tanh(k)
}

/** Sample saturationCurve into a Float32Array for a WaveShaper's `curve`/`mapping`,
 *  matching how loader.ts's softClipCurve is sampled in useOfflineRender.ts's
 *  limitMix() for the raw (non-Tone) offline pass. */
export function saturationCurveSamples(drive: number, length = 1024): Float32Array {
  const curve = new Float32Array(length)
  for (let i = 0; i < length; i++) curve[i] = saturationCurve((i / (length - 1)) * 2 - 1, drive)
  return curve
}
