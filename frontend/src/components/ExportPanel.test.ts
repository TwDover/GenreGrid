/*
 * GenreGrid — a style-based MIDI generator.
 * Copyright (C) 2026 Tw Dover
 *
 * This program is free software: you can redistribute it and/or modify it under
 * the terms of the GNU General Public License v3 or (at your option) any later
 * version. Distributed WITHOUT ANY WARRANTY. See <https://www.gnu.org/licenses/>.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { shallowMount, flushPromises } from '@vue/test-utils'

// The multitrack download resolves the save-name dialog and renders the queue —
// mock the interactive/audio composables so the test runs headless (roadmap-2 5.3).
const promptFilename = vi.fn().mockResolvedValue('mysong')
vi.mock('../composables/useDownloadPrompt', () => ({
  useDownloadPrompt: () => ({ promptFilename }),
}))
const offlineRender = vi.fn().mockResolvedValue(new Blob(['x']))
vi.mock('../composables/useMidiPlayer', () => ({
  useMidiPlayer: () => ({ isRecording: ref(false), offlineRender }),
}))
const completeJob = vi.fn()
const startJob = vi.fn(() => 'job1')
vi.mock('../composables/useRenderQueue', () => ({
  useRenderQueue: () => ({
    startJob, updateProgress: vi.fn(), completeJob, failJob: vi.fn(),
  }),
}))
vi.mock('../services/api', () => ({
  regeneratePart: vi.fn(), saveToLibrary: vi.fn(),
  bundleUrl: (id: string) => `/exports/${id}/bundle.zip`,
  sectionsUrl: (id: string) => `/exports/${id}/sections.zip`,
  downloadUrl: (u: string) => `http://api${u}`,
}))

import ExportPanel from './ExportPanel.vue'
import { useExportFormat } from '../composables/useExportFormat'
import type { GenerateResponse } from '../types/midi'

const response = (files: { part: string }[]): GenerateResponse => ({
  generation_id: 'abcd1234', style: 'lofi',
  files: files.map(f => ({ part: f.part, filename: `${f.part}.mid`, url: `/exports/abcd1234/${f.part}.mid` })),
  summary: { key: 'A minor', key_root: 'A', scale: 'minor', bpm: 90, bars: 8, complexity: 0.5, variation: 0.4, mode: 'loop' },
  seed: 1, auto_saved: false,
})

beforeEach(() => {
  promptFilename.mockClear().mockResolvedValue('mysong')
  completeJob.mockClear()
  startJob.mockClear()
  offlineRender.mockClear().mockResolvedValue(new Blob(['x']))
  useExportFormat().audioFormat.value = 'wav'   // reset the shared singleton
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, blob: async () => new Blob(['MThd']) }))
})

describe('ExportPanel — multitrack MIDI download (5.3)', () => {
  it('offers a Multitrack (.mid) button when a combined file exists', () => {
    const wrapper = shallowMount(ExportPanel, {
      props: { history: [response([{ part: 'chords' }, { part: 'combined' }])] },
    })
    const btn = wrapper.findAll('button').find(b => b.text().includes('Multitrack'))
    expect(btn).toBeTruthy()
  })

  it('hides the button when there is no combined file', () => {
    const wrapper = shallowMount(ExportPanel, {
      props: { history: [response([{ part: 'chords' }])] },
    })
    const btn = wrapper.findAll('button').find(b => b.text().includes('Multitrack'))
    expect(btn).toBeFalsy()
  })

  it('fetches the combined URL and completes a render-queue job on click', async () => {
    const wrapper = shallowMount(ExportPanel, {
      props: { history: [response([{ part: 'chords' }, { part: 'combined' }])] },
    })
    const btn = wrapper.findAll('button').find(b => b.text().includes('Multitrack'))!
    await btn.trigger('click')
    await flushPromises()
    expect(fetch).toHaveBeenCalledWith('http://api/exports/abcd1234/combined.mid')
    expect(completeJob).toHaveBeenCalledTimes(1)
  })
})

describe('ExportPanel — audio format toggle (5.2)', () => {
  it('threads the shared format into offlineRender and the download filename', async () => {
    useExportFormat().audioFormat.value = 'mp3'
    const wrapper = shallowMount(ExportPanel, {
      props: { history: [response([{ part: 'chords' }, { part: 'combined' }])] },
    })
    const mix = wrapper.findAll('button').find(b => b.text().includes('Mix'))!
    await mix.trigger('click')
    await flushPromises()
    // 6th arg is the format; the render-queue filename carries the .mp3 extension.
    expect(offlineRender.mock.calls[0][5]).toBe('mp3')
    expect(startJob).toHaveBeenCalledWith(expect.any(String), 'mysong.mp3')
    expect(promptFilename).toHaveBeenCalledWith('lofi_abcd1234', 'mp3', 'Export mix as MP3')
  })

  it('defaults to WAV and names stems per-part with the chosen extension', async () => {
    useExportFormat().audioFormat.value = 'ogg'
    const wrapper = shallowMount(ExportPanel, {
      props: { history: [response([{ part: 'chords' }, { part: 'drums' }, { part: 'combined' }])] },
    })
    const stems = wrapper.findAll('button').find(b => b.text().includes('Stems'))!
    await stems.trigger('click')
    await flushPromises()
    // One render per real part (not combined), each in the chosen format.
    expect(offlineRender.mock.calls.every(c => c[5] === 'ogg')).toBe(true)
    expect(startJob).toHaveBeenCalledWith(expect.any(String), 'mysong_chords.ogg')
    expect(startJob).toHaveBeenCalledWith(expect.any(String), 'mysong_drums.ogg')
  })
})
