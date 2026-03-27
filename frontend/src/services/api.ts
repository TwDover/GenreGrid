import type { StyleInfo, GenerateRequest, RegeneratePartRequest, GenerateResponse, FileInfo } from '../types/midi'

const BASE_URL = 'http://localhost:8000'

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

export function downloadUrl(url: string): string {
  return `${BASE_URL}${url}`
}
