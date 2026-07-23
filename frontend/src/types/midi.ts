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
export interface StyleInfo {
  id: string
  name: string
  bpm_range: [number, number]
  default_scale: string
  custom?: boolean
  has_prior?: boolean
  instruments?: Record<string, string>   // part role → instrument display name ("melody": "Alto Sax")
  voices?: Record<string, string>        // part role → playback voice id ("melody": "melody_lead")
}

/**
 * The full style-detail document returned by GET /styles/:id/detail and posted
 * back to POST /styles/custom. Every field the UI reads (radar metrics, editor
 * sliders) is enumerated and optional — the backend may omit any, and callers
 * always read them with a `?? default`. The index signature carries the many
 * additional backend fields the editor preserves on save but never reads
 * individually. Use this instead of `Record<string, any>` for style objects.
 */
export interface StyleConfig {
  id?: string
  name?: string
  bpm_range?: [number, number]
  velocity_base?: number
  groove_push?: number
  drums?: { hat_density?: number; swing?: number; triplet_probability?: number }
  melody?: { density?: number; stepwise_motion?: number; rest_probability?: number }
  bass?: { pattern_density?: number; sustain_bias?: number }
  chord_extensions?: { allow_7th?: number; allow_9th?: number }
  [key: string]: unknown
}

export interface GenerateRequest {
  style_id: string
  key: string
  scale: string
  bpm: number
  bars: number
  complexity: number
  variation: number
  parts: string[]
  mode: string
  seed?: number
  section_type?: string
  humanize: number
  custom_progression?: string[]
  blend_style_id?: string
  blend_amount: number
  use_priors?: boolean
}

export interface RegeneratePartRequest {
  generation_id: string
  part: string
  style_id: string
  key: string
  scale: string
  bpm: number
  bars: number
  complexity: number
  variation: number
  mode: string
  seed: number
}

export interface FileInfo {
  part: string
  filename: string
  url: string
}

export interface GenerateSummary {
  key: string
  key_root: string
  scale: string
  bpm: number
  bars: number
  complexity: number
  variation: number
  mode: string
  section_type?: string
}

export interface QualityScore {
  total: number
  harmonic: number
  separation: number
  rhythm: number
  contour: number
  density: number
  mix: number
  style_match?: number
  label: string
  flags: string[]
}

export interface GenerateResponse {
  generation_id: string
  style: string
  files: FileInfo[]
  summary: GenerateSummary
  seed: number
  quality?: QualityScore
  auto_saved: boolean
  progression?: string[]
  _elapsed?: string
}

export interface BatchGenerateRequest {
  base: GenerateRequest
  count: number
}

export interface SongSectionDef {
  section_type: string
  bars: number
  name?: string
  parts_mode?: string
  chorus_key?: boolean
  bridge_key?: boolean
  style_id?: string   // per-section style override (custom templates)
}

export interface BuildSongRequest {
  style_id: string
  key: string
  scale: string
  bpm: number
  complexity: number
  variation: number
  dynamics?: number
  humanize: number
  parts: string[]
  template: string
  seed?: number
  use_priors?: boolean
  chorus_key_shift?: number
  final_chorus_lift?: number
  custom_template?: SongSectionDef[]
  progression_override?: string[]   // pin an explicit roman-numeral progression
  blend_style_id?: string           // optional second style to blend with style_id
  blend_amount?: number             // 0..1 mix toward blend_style_id
}

export interface SongSectionResult {
  name: string
  section_type: string
  bars: number
  start_bar: number
  key: string
  quality?: number | null
}

export interface BuildSongResponse {
  generation_id: string
  style: string
  files: FileInfo[]
  seed: number
  template: string
  total_bars: number
  sections: SongSectionResult[]
  bpm: number
  key: string
  progression?: string[] | null   // resolved roman-numeral progression (shown + lockable)
  mixer?: Record<string, number> | null   // per-part gain, 1.0 = generated balance
}

export interface LibraryEntry {
  gen_id: string
  style_id: string
  key: string
  scale: string
  bpm: number
  bars: number
  seed: number
  saved_at: string
  quality: QualityScore
}
