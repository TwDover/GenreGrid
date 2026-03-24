export interface StyleInfo {
  id: string
  name: string
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
}

export interface FileInfo {
  part: string
  filename: string
  url: string
}

export interface GenerateSummary {
  key: string
  bpm: number
  bars: number
}

export interface GenerateResponse {
  generation_id: string
  style: string
  files: FileInfo[]
  summary: GenerateSummary
}
