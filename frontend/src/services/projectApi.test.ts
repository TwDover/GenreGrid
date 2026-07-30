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
// Roadmap 5.5 — portable project files: the .ggproj export URL and import POST.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { exportProjectUrl, importProject } from './api'

describe('portable project (.ggproj) api — 5.5', () => {
  afterEach(() => { vi.restoreAllMocks() })

  it('exportProjectUrl points at the export-project route for the id', () => {
    expect(exportProjectUrl('abc123')).toMatch(/\/export-project\/abc123$/)
  })

  describe('importProject', () => {
    beforeEach(() => { vi.restoreAllMocks() })

    it('POSTs the file as multipart and returns the parsed song', async () => {
      const song = { generation_id: 'newid', style: 'lofi', template: 'compact', total_bars: 8 }
      const fetchMock = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => song,
      })
      vi.stubGlobal('fetch', fetchMock)

      const file = new File([new Uint8Array([1, 2, 3])], 'my.ggproj')
      const result = await importProject(file)

      expect(result).toEqual(song)
      const [url, opts] = fetchMock.mock.calls[0]
      expect(url).toMatch(/\/import-project$/)
      expect(opts.method).toBe('POST')
      expect(opts.body).toBeInstanceOf(FormData)
      expect((opts.body as FormData).get('file')).toBe(file)
    })

    it('throws with the server detail on failure', async () => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
        ok: false,
        json: async () => ({ detail: 'Not a valid .ggproj file' }),
      }))
      await expect(importProject(new File([], 'bad.ggproj'))).rejects.toThrow('Not a valid .ggproj file')
    })
  })
})
