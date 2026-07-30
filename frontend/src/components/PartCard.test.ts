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

// PartCard leans on the audio/player composables and the export API; stub them so the
// card mounts headless. The piano-roll children are stubbed by shallowMount, so this
// test only exercises PartCard's own wiring (the ✎ editor toggle — roadmap 5.1).
const midi = { notes: [{ midi: 60, time: 0, duration: 0.5, velocity: 0.7, isPercussion: false }], duration: 2 }
vi.mock('../composables/useMidiPlayer', () => ({
  useMidiPlayer: () => ({
    toggle: vi.fn(), currentlyPlaying: ref(null), isLoading: ref(false),
    getMidiData: () => midi, prefetchMidi: vi.fn(), offlineRender: vi.fn(),
  }),
}))
vi.mock('../composables/useDownloadPrompt', () => ({ useDownloadPrompt: () => ({ promptFilename: vi.fn() }) }))
vi.mock('../composables/useToasts', () => ({ useToasts: () => ({ toast: vi.fn() }) }))
vi.mock('../composables/useRenderQueue', () => ({
  useRenderQueue: () => ({ startJob: vi.fn(), updateProgress: vi.fn(), completeJob: vi.fn(), failJob: vi.fn() }),
}))
vi.mock('../composables/useErrorLog', () => ({ logError: vi.fn() }))
vi.mock('../composables/useStyleCatalog', () => ({ instrumentLabel: () => null }))
vi.mock('../services/api', () => ({ downloadUrl: (u: string) => u, editPart: vi.fn() }))

import PartCard from './PartCard.vue'
import type { FileInfo } from '../types/midi'

const file: FileInfo = { part: 'melody', filename: 'melody.mid', url: '/exports/abcd1234/melody.mid' }

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, arrayBuffer: async () => new ArrayBuffer(8) }))
})

const editBtn = (w: VueWrapper) => w.findAll('button').find(b => b.text() === '✎')

describe('PartCard — piano-roll editor toggle', () => {
  it('shows the ✎ button only when editable', async () => {
    const plain = shallowMount(PartCard, { props: { file } })
    await flushPromises()
    expect(editBtn(plain)).toBeFalsy()

    const editable = shallowMount(PartCard, { props: { file, editable: true } })
    await flushPromises()
    expect(editBtn(editable)).toBeTruthy()
  })

  it('opens the editor when ✎ is clicked', async () => {
    const wrapper = shallowMount(PartCard, { props: { file, editable: true } })
    await flushPromises()
    expect(wrapper.findComponent({ name: 'PianoRollEditor' }).exists()).toBe(false)
    await editBtn(wrapper)!.trigger('click')
    expect(wrapper.findComponent({ name: 'PianoRollEditor' }).exists()).toBe(true)
  })
})
