import type { StyleInfo, GenerateRequest, RegeneratePartRequest, GenerateResponse, FileInfo, LibraryEntry } from '../types/midi'

const BASE_URL = (import.meta as any).env?.VITE_API_URL ?? 'http://localhost:8000'

export async function fetchStyles(): Promise<StyleInfo[]> {
  const res = await fetch(`${BASE_URL}/styles`)
  if (!res.ok) throw new Error('Failed to fetch styles')
  return res.json()
}

export async function generate(req: GenerateRequest): Promise<GenerateResponse> {
  const res = await fetch(`${BASE_URL}/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail ?? 'Generation failed')
  }
  return res.json()
}

export async function regeneratePart(req: RegeneratePartRequest): Promise<FileInfo> {
  const res = await fetch(`${BASE_URL}/regenerate-part`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail ?? 'Regeneration failed')
  }
  return res.json()
}

export async function saveToLibrary(response: GenerateResponse): Promise<void> {
  if (!response.quality) return
  await fetch(`${BASE_URL}/library/save`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      gen_id:   response.generation_id,
      style_id: response.style,
      key:      response.summary.key_root,
      scale:    response.summary.scale,
      bpm:      response.summary.bpm,
      bars:     response.summary.bars,
      seed:     response.seed,
      quality:  response.quality,
    }),
  })
}

export function downloadUrl(url: string): string {
  return `${BASE_URL}${url}`
}

export function bundleUrl(gen_id: string): string {
  return `${BASE_URL}/exports/${gen_id}/bundle.zip`
}

export async function fetchLibrary(style_id?: string): Promise<LibraryEntry[]> {
  const url = style_id ? `${BASE_URL}/library/${style_id}` : `${BASE_URL}/library/`
  const res = await fetch(url)
  if (!res.ok) throw new Error('Failed to fetch library')
  return res.json()
}

export async function fetchLibraryCounts(): Promise<Record<string, number>> {
  const res = await fetch(`${BASE_URL}/library/counts`)
  if (!res.ok) return {}
  return res.json()
}
