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
import type { StyleInfo, StyleConfig, GenerateRequest, RegeneratePartRequest, GenerateResponse, FileInfo, LibraryEntry, BatchGenerateRequest, BuildSongRequest, BuildSongResponse } from '../types/midi'

const BASE_URL = (() => {
  if (typeof window !== 'undefined' && window.electronAPI?.apiPort) {
    return `http://127.0.0.1:${window.electronAPI.apiPort}`
  }
  return import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
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

export interface SongPartCandidate { index: number; filename: string; url: string }

export async function rollSongPartCandidates(req: { generation_id: string; part: string; count?: number }): Promise<SongPartCandidate[]> {
  const res = await fetch(`${BASE_URL}/roll-song-part-candidates`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail ?? 'Rolling candidates failed')
  }
  return res.json()
}

export async function keepSongPartCandidate(req: { generation_id: string; part: string; index: number }): Promise<FileInfo> {
  const res = await fetch(`${BASE_URL}/keep-song-part-candidate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail ?? 'Keeping candidate failed')
  }
  return res.json()
}

export async function regenerateSongSection(req: { generation_id: string; section_index: number; locked_parts?: string[] }): Promise<FileInfo[]> {
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

export async function buildSongFromMelody(
  file: File,
  params: {
    style_id: string; template: string; parts: string[]
    complexity: number; variation: number; humanize: number
    use_priors?: boolean; chorus_key_shift?: number; final_chorus_lift?: number; seed?: number
  },
): Promise<BuildSongResponse> {
  const fd = new FormData()
  fd.append('file', file)
  fd.append('style_id', params.style_id)
  fd.append('template', params.template)
  fd.append('parts', params.parts.join(','))
  fd.append('complexity', String(params.complexity))
  fd.append('variation', String(params.variation))
  fd.append('humanize', String(params.humanize))
  fd.append('use_priors', String(params.use_priors ?? false))
  fd.append('chorus_key_shift', String(params.chorus_key_shift ?? 0))
  fd.append('final_chorus_lift', String(params.final_chorus_lift ?? 1))
  if (params.seed != null) fd.append('seed', String(params.seed))
  const res = await fetch(`${BASE_URL}/build-song-from-melody`, { method: 'POST', body: fd })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail ?? 'Melody import failed')
  }
  return res.json()
}

export async function setPartGain(req: { generation_id: string; part: string; gain: number }): Promise<FileInfo> {
  const res = await fetch(`${BASE_URL}/set-part-gain`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail ?? 'Volume change failed')
  }
  return res.json()
}

export async function listSongs(): Promise<BuildSongResponse[]> {
  const res = await fetch(`${BASE_URL}/songs`)
  if (!res.ok) return []
  return res.json()
}

export interface SongVersion { id: string; saved_at: string }

export async function listSongVersions(generationId: string): Promise<SongVersion[]> {
  const res = await fetch(`${BASE_URL}/song-versions/${generationId}`)
  if (!res.ok) return []
  return res.json()
}

export async function restoreSongVersion(req: { generation_id: string; version_id: string }): Promise<FileInfo[]> {
  const res = await fetch(`${BASE_URL}/restore-song-version`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail ?? 'Restore failed')
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

export async function fetchStyleDetail(styleId: string): Promise<StyleConfig> {
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

export async function rebuildSongProgression(req: { generation_id: string; progression: string[] }): Promise<BuildSongResponse> {
  const res = await fetch(`${BASE_URL}/rebuild-song-progression`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail ?? 'Rebuilding progression failed')
  }
  return res.json()
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

export async function saveCustomStyle(style: StyleConfig): Promise<StyleConfig> {
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

export async function editPart(req: {
  generation_id: string
  part: string
  notes: { pitch: number; start: number; duration: number; velocity: number }[]
}): Promise<FileInfo> {
  const res = await fetch(`${BASE_URL}/edit-part`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail ?? 'Saving note edits failed')
  }
  return res.json()
}
