export interface StyleInfo {
  id: string
  name: string
  bpm_range: [number, number]
  default_scale: string
  custom?: boolean
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
  register: number
  rhythm: number
  density: number
  mix: number
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

export interface BuildSongRequest {
  style_id: string
  key: string
  scale: string
  bpm: number
  complexity: number
  variation: number
  humanize: number
  parts: string[]
  template: string
  seed?: number
}

export interface SongSectionResult {
  name: string
  section_type: string
  bars: number
  start_bar: number
  key: string
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
