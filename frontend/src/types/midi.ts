export interface StyleInfo {
  id: string
  name: string
  bpm_range: [number, number]
  default_scale: string
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
}
