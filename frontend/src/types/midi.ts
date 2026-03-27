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

export interface GenerateResponse {
  generation_id: string
  style: string
  files: FileInfo[]
  summary: GenerateSummary
  seed: number
}
