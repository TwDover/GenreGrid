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
import { shallowMount, flushPromises, type VueWrapper } from '@vue/test-utils'

// Roadmap 9.2 — timeline reorder/insert/duplicate/delete. Stub every composable
// SongResult.vue touches so it mounts headless (mirrors PartCard.test.ts).
const rearrangeSongSections = vi.fn()
const regenerateSongSection = vi.fn()
const moveNoteRegion = vi.fn()
const setNoteRegionLoop = vi.fn()
const deleteNoteRegion = vi.fn()
vi.mock('../services/api', () => ({
  downloadUrl: (u: string) => u,
  exportProjectUrl: (id: string) => `/exports/${id}.ggproj`,
  regenerateSongPart: vi.fn(),
  regenerateSongSection: (...a: unknown[]) => regenerateSongSection(...a),
  rearrangeSongSections: (...a: unknown[]) => rearrangeSongSections(...a),
  undoSongPart: vi.fn(),
  listSongVersions: vi.fn().mockResolvedValue([]),
  restoreSongVersion: vi.fn(),
  setPartGain: vi.fn(),
  rollSongPartCandidates: vi.fn(),
  keepSongPartCandidate: vi.fn(),
  rebuildSongProgression: vi.fn(),
  moveNoteRegion: (...a: unknown[]) => moveNoteRegion(...a),
  setNoteRegionLoop: (...a: unknown[]) => setNoteRegionLoop(...a),
  deleteNoteRegion: (...a: unknown[]) => deleteNoteRegion(...a),
}))
vi.mock('../composables/useMidiPlayer', () => ({
  useMidiPlayer: () => ({
    toggle: vi.fn(), stop: vi.fn(), currentlyPlaying: ref(null),
    seek: vi.fn(), positionSeconds: ref(0), offlineRender: vi.fn(), cue: vi.fn(),
  }),
}))
vi.mock('../composables/useToasts', () => ({ useToasts: () => ({ toast: vi.fn() }) }))
vi.mock('../composables/useDownloadPrompt', () => ({ useDownloadPrompt: () => ({ promptFilename: vi.fn() }) }))
vi.mock('../composables/useRenderQueue', () => ({
  useRenderQueue: () => ({ startJob: vi.fn(), updateProgress: vi.fn(), completeJob: vi.fn(), failJob: vi.fn() }),
}))
vi.mock('../composables/useStyleCatalog', () => ({ useStyleCatalog: () => ({ catalog: ref(new Map()) }) }))
vi.mock('../composables/useExportFormat', () => ({ useExportFormat: () => ({ audioFormat: ref('wav') }) }))
vi.mock('../composables/useErrorLog', () => ({ logError: vi.fn() }))

import SongResult from './SongResult.vue'
import type { BuildSongResponse } from '../types/midi'

const fakeSections = [
  { name: 'Verse', section_type: 'verse', bars: 8, start_bar: 0, key: 'C', quality: 0.9, parts_mode: 'no_arp', chorus_key: false, bridge_key: false, style_id: null },
  { name: 'Chorus', section_type: 'chorus', bars: 8, start_bar: 8, key: 'C', quality: 0.85, parts_mode: 'full', chorus_key: true, bridge_key: false, style_id: null },
  { name: 'Bridge', section_type: 'bridge', bars: 4, start_bar: 16, key: 'C', quality: 0.8, parts_mode: 'full', chorus_key: false, bridge_key: true, style_id: null },
  { name: 'End', section_type: 'ending', bars: 1, start_bar: 20, key: 'C' },
]

const fakeResult: BuildSongResponse = {
  generation_id: 'abcd1234', style: 'lofi', seed: 1, template: 'custom', total_bars: 21,
  bpm: 90, key: 'C minor', progression: [],
  sections: fakeSections,
  files: [
    { part: 'melody', filename: 'melody.mid', url: '/exports/abcd1234/melody.mid' },
    { part: 'chords', filename: 'chords.mid', url: '/exports/abcd1234/chords.mid' },
  ],
}

const rearrangedResult: BuildSongResponse = {
  ...fakeResult,
  sections: [fakeSections[1], fakeSections[0], fakeSections[2], fakeSections[3]],
  files: fakeResult.files,
}

const fakeRegion = {
  id: 'r1', part: 'melody', start_bar: 2, bars: 1, loop_count: 1,
  notes: [{ pitch: 67, start: 0, duration: 1, velocity: 100 }],
}
const resultWithRegion: BuildSongResponse = { ...fakeResult, note_regions: [fakeRegion] }

beforeEach(() => {
  rearrangeSongSections.mockReset().mockResolvedValue(rearrangedResult)
  regenerateSongSection.mockReset().mockResolvedValue([])
  moveNoteRegion.mockReset()
  setNoteRegionLoop.mockReset()
  deleteNoteRegion.mockReset()
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, arrayBuffer: async () => new ArrayBuffer(8) }))
})

const mountResult = () => shallowMount(SongResult, { props: { result: fakeResult, label: 'My Song' } })
const tlBlocks = (w: VueWrapper) => w.findAll('.sr-tl-block')
const dt = () => ({ setData: vi.fn(), effectAllowed: '' }) as unknown as DataTransfer

describe('SongResult — timeline rearrange (roadmap 9.2, slice A)', () => {
  it('reorders sections via drag-and-drop and emits the rebuilt result', async () => {
    const wrapper = mountResult()
    const blocks = tlBlocks(wrapper)
    expect(blocks).toHaveLength(4)   // verse, chorus, bridge, ending

    await blocks[0].trigger('dragstart', { dataTransfer: dt() })
    await blocks[2].trigger('dragover', { clientX: 999, dataTransfer: dt() })
    await blocks[2].trigger('drop', { dataTransfer: dt() })
    await flushPromises()

    expect(rearrangeSongSections).toHaveBeenCalledTimes(1)
    const payload = rearrangeSongSections.mock.calls[0][0]
    expect(payload.generation_id).toBe('abcd1234')
    // Verse (source_index 0) dragged past Bridge (index 2, dropped on its right
    // half) — Chorus and Bridge should now precede Verse.
    expect(payload.sections.map((s: { section_type: string }) => s.section_type))
      .toEqual(['chorus', 'bridge', 'verse'])
    expect(payload.sections.every((s: { source_index: number }) => s.source_index !== null)).toBe(true)

    expect(wrapper.emitted('rebuilt')).toBeTruthy()
    expect(wrapper.emitted('rebuilt')![0][0]).toEqual(rearrangedResult)
  })

  it('does not reorder past the ending block', async () => {
    const wrapper = mountResult()
    const blocks = tlBlocks(wrapper)
    await blocks[0].trigger('dragstart', { dataTransfer: dt() })
    await blocks[3].trigger('dragover', { clientX: 0, dataTransfer: dt() })   // the ending block
    await blocks[3].trigger('drop', { dataTransfer: dt() })
    await flushPromises()
    expect(rearrangeSongSections).not.toHaveBeenCalled()
  })

  it('deletes a section', async () => {
    const wrapper = mountResult()
    const delBtn = wrapper.findAll('.sr-tl-controls button').find(b => b.text() === '✕')!
    await delBtn.trigger('click')
    await flushPromises()
    expect(rearrangeSongSections).toHaveBeenCalledTimes(1)
    const payload = rearrangeSongSections.mock.calls[0][0]
    expect(payload.sections).toHaveLength(2)
    expect(payload.sections.map((s: { section_type: string }) => s.section_type)).toEqual(['chorus', 'bridge'])
  })

  it('duplicates a section, keeping the same source_index for both copies', async () => {
    const wrapper = mountResult()
    const dupBtn = wrapper.findAll('.sr-tl-controls button').find(b => b.text() === '⧉')!
    await dupBtn.trigger('click')
    await flushPromises()
    expect(rearrangeSongSections).toHaveBeenCalledTimes(1)
    const payload = rearrangeSongSections.mock.calls[0][0]
    expect(payload.sections).toHaveLength(4)
    expect(payload.sections[0].section_type).toBe('verse')
    expect(payload.sections[1].section_type).toBe('verse')
    expect(payload.sections[0].source_index).toBe(payload.sections[1].source_index)
  })

  it('inserts a section of the chosen type, with no source_index (fresh seed)', async () => {
    const wrapper = mountResult()
    await wrapper.find('.sr-tl-insert').setValue('bridge')
    await flushPromises()
    expect(rearrangeSongSections).toHaveBeenCalledTimes(1)
    const payload = rearrangeSongSections.mock.calls[0][0]
    expect(payload.sections).toHaveLength(4)
    const inserted = payload.sections[payload.sections.length - 1]
    expect(inserted.section_type).toBe('bridge')
    expect(inserted.bridge_key).toBe(true)
    expect(inserted.source_index == null).toBe(true)
  })

  it('resizes a section by dragging its right edge, reusing its source_index', async () => {
    const wrapper = mountResult()
    const blocks = tlBlocks(wrapper)
    vi.spyOn(blocks[0].element, 'getBoundingClientRect').mockReturnValue({ width: 80 } as DOMRect)
    const handle = blocks[0].find('.sr-tl-resize-handle')
    expect(handle.exists()).toBe(true)

    await handle.trigger('mousedown', { clientX: 0 })
    window.dispatchEvent(new MouseEvent('mousemove', { clientX: 25 }))   // 80px / 8 bars = 10px/bar → +2.5 → +3 bars
    window.dispatchEvent(new MouseEvent('mouseup', { clientX: 25 }))
    await flushPromises()

    expect(rearrangeSongSections).toHaveBeenCalledTimes(1)
    const payload = rearrangeSongSections.mock.calls[0][0]
    expect(payload.sections[0].section_type).toBe('verse')
    expect(payload.sections[0].bars).toBe(11)
    expect(payload.sections[0].source_index).toBe(0)
  })

  it('a resize drag does not also trigger seek-to-section on release', async () => {
    const wrapper = mountResult()
    const blocks = tlBlocks(wrapper)
    vi.spyOn(blocks[0].element, 'getBoundingClientRect').mockReturnValue({ width: 80 } as DOMRect)
    const handle = blocks[0].find('.sr-tl-resize-handle')

    await handle.trigger('mousedown', { clientX: 0 })
    window.dispatchEvent(new MouseEvent('mousemove', { clientX: 25 }))
    window.dispatchEvent(new MouseEvent('mouseup', { clientX: 25 }))
    await blocks[0].trigger('click')
    await flushPromises()

    // The resize itself calls rearrangeSongSections once; the swallowed click
    // must not have also started playback-seek (no second API call, no throw).
    expect(rearrangeSongSections).toHaveBeenCalledTimes(1)
  })

  it('blocks every structural edit while a part is locked, with no API call', async () => {
    const wrapper = mountResult()
    const partCard = wrapper.findComponent({ name: 'PartCard' })
    expect(partCard.exists()).toBe(true)
    await partCard.vm.$emit('toggle-lock', 'melody')
    await flushPromises()

    expect(wrapper.find('.sr-error').text()).toContain('melody')

    const blocks = tlBlocks(wrapper)
    expect(blocks[0].attributes('draggable')).toBe('false')

    vi.spyOn(blocks[0].element, 'getBoundingClientRect').mockReturnValue({ width: 80 } as DOMRect)
    await blocks[0].find('.sr-tl-resize-handle').trigger('mousedown', { clientX: 0 })
    window.dispatchEvent(new MouseEvent('mousemove', { clientX: 25 }))
    window.dispatchEvent(new MouseEvent('mouseup', { clientX: 25 }))
    await flushPromises()
    expect(rearrangeSongSections).not.toHaveBeenCalled()

    const delBtn = wrapper.findAll('.sr-tl-controls button').find(b => b.text() === '✕')!
    expect((delBtn.element as HTMLButtonElement).disabled).toBe(true)
    await delBtn.trigger('click')
    expect((wrapper.find('.sr-tl-insert').element as HTMLSelectElement).disabled).toBe(true)
    await wrapper.find('.sr-tl-insert').setValue('bridge')
    await flushPromises()

    expect(rearrangeSongSections).not.toHaveBeenCalled()
  })
})

describe('SongResult — note regions (roadmap 9.2 follow-up)', () => {
  const mountWithRegion = () => shallowMount(SongResult, { props: { result: resultWithRegion, label: 'My Song' } })
  const regionTrack = (w: VueWrapper) => w.findComponent({ name: 'NoteRegionTrack' })

  it('renders a region row only for parts that have a region', async () => {
    const wrapper = mountWithRegion()
    await flushPromises()
    const track = regionTrack(wrapper)
    expect(track.exists()).toBe(true)
    expect(track.props('regions')).toEqual([fakeRegion])
    expect(track.props('totalBars')).toBe(resultWithRegion.total_bars)
  })

  it('renders no region row when the song has none', async () => {
    const wrapper = mountResult()
    await flushPromises()
    expect(regionTrack(wrapper).exists()).toBe(false)
  })

  it('moves a region and refreshes the part/song cache-bust version', async () => {
    moveNoteRegion.mockResolvedValue({
      file: { part: 'melody', filename: 'melody.mid', url: '/exports/abcd1234/melody.mid' },
      regions: [{ ...fakeRegion, start_bar: 5 }],
    })
    const wrapper = mountWithRegion()
    await flushPromises()
    await regionTrack(wrapper).vm.$emit('move', 'r1', 5)
    await flushPromises()

    expect(moveNoteRegion).toHaveBeenCalledWith('r1', { generation_id: 'abcd1234', new_start_bar: 5 })
    expect(regionTrack(wrapper).props('regions')).toEqual([{ ...fakeRegion, start_bar: 5 }])
  })

  it('changes a region loop count', async () => {
    setNoteRegionLoop.mockResolvedValue({
      file: { part: 'melody', filename: 'melody.mid', url: '/exports/abcd1234/melody.mid' },
      regions: [{ ...fakeRegion, loop_count: 3 }],
    })
    const wrapper = mountWithRegion()
    await flushPromises()
    await regionTrack(wrapper).vm.$emit('set-loop', 'r1', 3)
    await flushPromises()

    expect(setNoteRegionLoop).toHaveBeenCalledWith('r1', { generation_id: 'abcd1234', loop_count: 3 })
    expect(regionTrack(wrapper).props('regions')).toEqual([{ ...fakeRegion, loop_count: 3 }])
  })

  it('deletes a region, removing its row', async () => {
    deleteNoteRegion.mockResolvedValue({
      file: { part: 'melody', filename: 'melody.mid', url: '/exports/abcd1234/melody.mid' },
      regions: [],
    })
    const wrapper = mountWithRegion()
    await flushPromises()
    await regionTrack(wrapper).vm.$emit('delete', 'r1')
    await flushPromises()

    expect(deleteNoteRegion).toHaveBeenCalledWith('abcd1234', 'r1')
    expect(regionTrack(wrapper).exists()).toBe(false)
  })

  it('replaces an overlapping region client-side when a part reports a newly-saved take', async () => {
    const wrapper = mountWithRegion()
    await flushPromises()
    const partCard = wrapper.findComponent({ name: 'PartCard' })
    const replacement = { id: 'r2', part: 'melody', start_bar: 2, bars: 2, loop_count: 1, notes: [] }
    await partCard.vm.$emit('region-saved', 'melody', replacement)
    await flushPromises()

    // r1 (bars 2-3) overlaps r2 (bars 2-4) on the same part -> replaced, not stacked.
    expect(regionTrack(wrapper).props('regions')).toEqual([replacement])
  })

  it('does not disable region controls just because a part is locked', async () => {
    const wrapper = mountWithRegion()
    const partCard = wrapper.findComponent({ name: 'PartCard' })
    await partCard.vm.$emit('toggle-lock', 'melody')
    await flushPromises()
    expect(regionTrack(wrapper).props('disabled')).toBe(false)
  })
})
