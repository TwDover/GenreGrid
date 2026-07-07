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
import type { StyleInfo, GenerateRequest, RegeneratePartRequest, GenerateResponse, FileInfo, LibraryEntry, BatchGenerateRequest, BuildSongRequest, BuildSongResponse } from '../types/midi'

const BASE_URL = (() => {
  if (typeof window !== 'undefined' && (window as any).electronAPI?.apiPort) {
    return `http://127.0.0.1:${(window as any).electronAPI.apiPort}`
  }
  return (import.meta as any).env?.VITE_API_URL ?? 'http://localhost:8000'
})()

export async function fetchStyles(): Promise<StyleInfo[]> {
  const res = await fetch(`${BASE_URL}/styles`)
  if (!res.ok) throw new Error('Failed to fetch styles')
  return res.json()
}

export async function generate(
  req: GenerateRequest,
  onProgress?: (attempt: number, total: number) => void,
): Promise<GenerateResponse> {
  const res = await fetch(`${BASE_URL}/generate-stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!res.ok || !res.body) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail ?? 'Generation failed')
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      const msg = JSON.parse(line.slice(6))
      if (msg.type === 'progress' && onProgress) {
        onProgress(msg.attempt, msg.total)
      } else if (msg.type === 'done') {
        return msg.result as GenerateResponse
      } else if (msg.type === 'error') {
        throw new Error(msg.message)
      }
    }
  }
  throw new Error('Stream ended without a result')
}

export async function batchGenerate(req: BatchGenerateRequest): Promise<GenerateResponse[]> {
  const res = await fetch(`${BASE_URL}/batch-generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail ?? 'Batch generation failed')
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

export async function regenerateSongPart(req: { generation_id: string; part: string }): Promise<FileInfo> {
  const res = await fetch(`${BASE_URL}/regenerate-song-part`, {
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

export async function regenerateSongSection(req: { generation_id: string; section_index: number }): Promise<FileInfo[]> {
  const res = await fetch(`${BASE_URL}/regenerate-song-section`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail ?? 'Section regeneration failed')
  }
  return res.json()
}

export async function undoSongPart(req: { generation_id: string; part: string }): Promise<FileInfo> {
  const res = await fetch(`${BASE_URL}/undo-song-part`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail ?? 'Undo failed')
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

export function sectionsUrl(gen_id: string): string {
  return `${BASE_URL}/exports/${gen_id}/sections.zip`
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

export async function fetchStyleDetail(styleId: string): Promise<Record<string, any>> {
  const res = await fetch(`${BASE_URL}/styles/${styleId}/detail`)
  if (!res.ok) throw new Error('Failed to fetch style detail')
  return res.json()
}

export async function arrangeDownload(entries: { generation_id: string; filename: string }[]): Promise<Blob> {
  const res = await fetch(`${BASE_URL}/arrange`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ entries }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail ?? 'Failed to build arrangement')
  }
  return res.blob()
}

export async function buildSong(req: BuildSongRequest): Promise<BuildSongResponse> {
  const res = await fetch(`${BASE_URL}/build-song`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail ?? 'Song generation failed')
  }
  return res.json()
}

export async function saveCustomStyle(style: Record<string, any>): Promise<Record<string, any>> {
  const res = await fetch(`${BASE_URL}/styles/custom`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(style),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail ?? 'Failed to save custom style')
  }
  return res.json()
}
