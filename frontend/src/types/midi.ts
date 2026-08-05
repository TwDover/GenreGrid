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
  progression_templates?: string[][]     // the style's roman-numeral progressions, for the picker
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
  time_signature?: string
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

/** A recorded audio take (roadmap 9.4) — one per generation, placed at a
 * bar-aligned region. Deliberately not a FileInfo: it has no MIDI channel/
 * program, so it stays out of the PLAYER_PARTS-driven part machinery. */
export interface AudioClipInfo {
  part: 'audio'
  filename: string
  url: string
  start_bar: number
  bars: number
}

/** A recorded MIDI take (roadmap 9.1) tracked as an independent, draggable,
 * loopable region on a part's timeline (roadmap 9.2 follow-up) — distinct from
 * the section it was recorded into. `notes` are the take's exact captured
 * content, relative to the region's own start (beat 0 = region start); the
 * part's stem always holds the *expansion* of that content (`loop_count`
 * copies starting at `start_bar`), merged in alongside anything else on the
 * part. Created only by finishing a recording take — see PianoRollEditor.vue/
 * PartCard.vue. */
export interface NoteRegionInfo {
  id: string
  part: string
  start_bar: number
  bars: number
  loop_count: number
  notes: { pitch: number; start: number; duration: number; velocity: number }[]
}

/** Returned by the region endpoints that rewrite a part's stem (move/
 * loop-change/delete) — the rewritten stem plus the generation's full,
 * current region list. */
export interface NoteRegionMutationResponse {
  file: FileInfo
  regions: NoteRegionInfo[]
}

export interface GenerateSummary {
  key: string
  key_root: string
  scale: string
  time_signature?: string
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

export interface RearrangeSectionDef extends SongSectionDef {
  // Index into the song's CURRENT (pre-edit) section list whose original seed
  // this entry reuses (content stability across move/resize/duplicate).
  // undefined/null = brand-new content, freshly seeded and quality-searched.
  source_index?: number | null
}

export interface BuildSongRequest {
  style_id: string
  key: string
  scale: string
  time_signature?: string
  bpm: number
  complexity: number
  variation: number
  dynamics?: number
  tempo_automation?: number          // tempo movement: 0 = flat, 0.5 = subtle, 1 = expressive
  humanize: number
  parts: string[]
  template: string
  seed?: number
  use_priors?: boolean
  chorus_key_shift?: number
  final_chorus_lift?: number
  custom_template?: SongSectionDef[]
  progression_override?: string[]   // pin an explicit roman-numeral progression
  progression_text?: string         // free-typed romans or chord names ("Am F C G"); parsed server-side
  blend_style_id?: string           // optional second style to blend with style_id
  blend_amount?: number             // 0..1 mix toward blend_style_id
}

export interface HummedNote {
  pitch: number
  start: number      // beats
  duration: number   // beats
  velocity: number
}

export interface SongSectionResult {
  name: string
  section_type: string
  bars: number
  start_bar: number
  key: string
  quality?: number | null
  parts_mode?: string
  chorus_key?: boolean
  bridge_key?: boolean
  style_id?: string | null
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
  audio_clip?: AudioClipInfo | null   // recorded take (roadmap 9.4), if any
  note_regions?: NoteRegionInfo[] | null   // movable/loopable MIDI regions (roadmap 9.2 follow-up), if any
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
