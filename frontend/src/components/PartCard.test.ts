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
const channelMuted = ref<Record<string, boolean>>({ melody: false, bass: false })
const toggleMute = vi.fn((ch: string) => { channelMuted.value = { ...channelMuted.value, [ch]: !channelMuted.value[ch] } })
const soloPart = vi.fn()
vi.mock('../composables/useMidiPlayer', () => ({
  PLAYER_PARTS: ['drums', 'bass', 'chords', 'melody', 'arpeggio', 'pads', 'counter_melody'],
  useMidiPlayer: () => ({
    toggle: vi.fn(), currentlyPlaying: ref(null), isLoading: ref(false),
    getMidiData: () => midi, prefetchMidi: vi.fn(), offlineRender: vi.fn(),
    setMidiData: vi.fn(), channelMuted, toggleMute, soloPart,
  }),
}))
vi.mock('../composables/useDownloadPrompt', () => ({ useDownloadPrompt: () => ({ promptFilename: vi.fn() }) }))
vi.mock('../composables/useToasts', () => ({ useToasts: () => ({ toast: vi.fn() }) }))
vi.mock('../composables/useRenderQueue', () => ({
  useRenderQueue: () => ({ startJob: vi.fn(), updateProgress: vi.fn(), completeJob: vi.fn(), failJob: vi.fn() }),
}))
vi.mock('../composables/useErrorLog', () => ({ logError: vi.fn() }))
vi.mock('../composables/useStyleCatalog', () => ({ instrumentLabel: () => null }))
vi.mock('../services/api', () => ({ downloadUrl: (u: string) => u, editPart: vi.fn(), saveNoteRegion: vi.fn() }))

import PartCard from './PartCard.vue'
import type { FileInfo } from '../types/midi'
import { editPart, saveNoteRegion } from '../services/api'
import { logError } from '../composables/useErrorLog'

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

describe('PartCard — per-part mute (DAW-style, on the instrument row)', () => {
  const muteBtn = (w: VueWrapper) => w.findAll('button').find(b => b.text() === 'M')

  beforeEach(() => {
    channelMuted.value = { melody: false, bass: false }
    toggleMute.mockClear(); soloPart.mockClear()
  })

  it('mutes and unmutes the part on click', async () => {
    const wrapper = shallowMount(PartCard, { props: { file } })
    await flushPromises()
    const btn = muteBtn(wrapper)!
    expect(btn).toBeTruthy()
    expect(btn.classes()).not.toContain('muted')

    await btn.trigger('click')
    expect(toggleMute).toHaveBeenCalledWith('melody')
    expect(muteBtn(wrapper)!.classes()).toContain('muted')   // reflects shared mute state
  })

  it('shift-click solos the part', async () => {
    const wrapper = shallowMount(PartCard, { props: { file } })
    await flushPromises()
    await muteBtn(wrapper)!.trigger('click', { shiftKey: true })
    expect(soloPart).toHaveBeenCalledWith('melody')
    expect(toggleMute).not.toHaveBeenCalled()
  })

  it('hides mute for the combined/song mixdown (no channel of its own)', async () => {
    const combined: FileInfo = { part: 'combined', filename: 'combined.mid', url: '/exports/abcd1234/combined.mid' }
    const wrapper = shallowMount(PartCard, { props: { file: combined } })
    await flushPromises()
    expect(muteBtn(wrapper)).toBeFalsy()
  })
})

describe('PartCard — automation round-trip through saveEdits (roadmap 9.3)', () => {
  const saveBtn = (w: VueWrapper) => w.findAll('button').find(b => b.text() === 'Save edits')

  beforeEach(() => { vi.mocked(editPart).mockClear() })

  it('converts drawn automation breakpoints (seconds/0..1) to beats and includes them in the /edit-part payload', async () => {
    vi.mocked(editPart).mockResolvedValue({ part: 'melody', filename: 'melody.mid', url: file.url })
    const wrapper = shallowMount(PartCard, { props: { file, editable: true } })
    await flushPromises()
    await editBtn(wrapper)!.trigger('click')

    const editor = wrapper.findComponent({ name: 'PianoRollEditor' })
    editor.vm.$emit('notes-changed', midi.notes, true)
    // No real tempo header parses in this test (mocked fetch returns garbage bytes),
    // so PartCard falls back to its default secondsPerBeat (0.5 = 120bpm): 1s -> 2 beats.
    editor.vm.$emit('automation-changed', {
      volume: [{ time: 1, value: 0.8 }],
      pan: [{ time: 0, value: 0.25 }],
    }, true)
    await flushPromises()

    await saveBtn(wrapper)!.trigger('click')
    await flushPromises()

    expect(editPart).toHaveBeenCalledTimes(1)
    const payload = vi.mocked(editPart).mock.calls[0][0]
    expect(payload.automation?.volume).toEqual([{ beat: 2, value: 0.8 }])
    expect(payload.automation?.pan).toEqual([{ beat: 0, value: 0.25 }])
  })

  it('falls back to the cached automation when the editor never emitted its own', async () => {
    vi.mocked(editPart).mockResolvedValue({ part: 'melody', filename: 'melody.mid', url: file.url })
    const wrapper = shallowMount(PartCard, { props: { file, editable: true } })
    await flushPromises()
    await editBtn(wrapper)!.trigger('click')

    const editor = wrapper.findComponent({ name: 'PianoRollEditor' })
    editor.vm.$emit('notes-changed', midi.notes, true)   // a note-only edit — automation untouched
    await flushPromises()

    await saveBtn(wrapper)!.trigger('click')
    await flushPromises()

    expect(editPart).toHaveBeenCalledTimes(1)
    const payload = vi.mocked(editPart).mock.calls[0][0]
    expect(payload.automation).toEqual({ volume: [], pan: [] })   // midi has no automation field -> empty fallback
  })
})

describe('PartCard — note-region save flow (roadmap 9.2 follow-up)', () => {
  const saveBtn = (w: VueWrapper) => w.findAll('button').find(b => b.text() === 'Save edits')
  // shallowMount's default auto-stubs have no `markSaved` (the real components
  // expose it via defineExpose) — saveEdits() calls `rollRef.value?.markSaved()`
  // unconditionally, which throws on the bare auto-stub and aborts the rest of
  // saveEdits (including the region-save logic under test) before it runs.
  // Provide minimal named stubs with a no-op markSaved so saveEdits() actually
  // completes, same as it would against the real components.
  const stubs = {
    PianoRoll: { name: 'PianoRoll', template: '<div/>', methods: { markSaved() {} } },
    PianoRollEditor: { name: 'PianoRollEditor', template: '<div/>', methods: { markSaved() {} } },
  }
  function mountEditable() {
    return shallowMount(PartCard, { props: { file, editable: true }, global: { stubs } })
  }

  beforeEach(() => {
    vi.mocked(editPart).mockClear()
    vi.mocked(saveNoteRegion).mockClear()
  })

  it('registers a just-recorded take as a region once its notes are saved, converting seconds to beats via the real tempo map', async () => {
    vi.mocked(editPart).mockResolvedValue({ part: 'melody', filename: 'melody.mid', url: file.url })
    vi.mocked(saveNoteRegion).mockResolvedValue({
      id: 'r1', part: 'melody', start_bar: 2, bars: 1, loop_count: 1,
      notes: [{ pitch: 67, start: 1, duration: 1, velocity: 102 }],
    })
    const wrapper = mountEditable()
    await flushPromises()
    await editBtn(wrapper)!.trigger('click')

    const editor = wrapper.findComponent({ name: 'PianoRollEditor' })
    // No real tempo header parses in this test (mocked fetch returns garbage
    // bytes), so PartCard falls back to secondsPerBeat = 0.5 (120bpm): 1s = 2 beats.
    // Region: 4s..6s (beats 8..12); one note at relative time 0.5s, duration 0.5s
    // (absolute 4.5s..5.0s = beats 9..10, i.e. 1..2 relative to the region's beat 8).
    editor.vm.$emit('region-captured', {
      startSec: 4, endSec: 6,
      notes: [{ midi: 67, time: 0.5, duration: 0.5, velocity: 0.8, isPercussion: false }],
    })
    editor.vm.$emit('notes-changed', midi.notes, true)
    await flushPromises()

    await saveBtn(wrapper)!.trigger('click')
    await flushPromises()

    expect(editPart).toHaveBeenCalledTimes(1)   // the take's notes save through the ordinary path first
    expect(saveNoteRegion).toHaveBeenCalledTimes(1)
    const payload = vi.mocked(saveNoteRegion).mock.calls[0][0]
    expect(payload.generation_id).toBe('abcd1234')
    expect(payload.part).toBe('melody')
    expect(payload.start_bar).toBe(2)
    expect(payload.bars).toBe(1)
    expect(payload.notes).toEqual([{ pitch: 67, start: 1, duration: 1, velocity: 102 }])
    expect(wrapper.emitted('region-saved')?.[0]).toEqual(['melody', {
      id: 'r1', part: 'melody', start_bar: 2, bars: 1, loop_count: 1,
      notes: [{ pitch: 67, start: 1, duration: 1, velocity: 102 }],
    }])
  })

  it('does not call saveNoteRegion for a plain edit with no pending recorded take', async () => {
    vi.mocked(editPart).mockResolvedValue({ part: 'melody', filename: 'melody.mid', url: file.url })
    const wrapper = mountEditable()
    await flushPromises()
    await editBtn(wrapper)!.trigger('click')

    const editor = wrapper.findComponent({ name: 'PianoRollEditor' })
    editor.vm.$emit('notes-changed', midi.notes, true)   // an ordinary hand edit, no recording involved
    await flushPromises()

    await saveBtn(wrapper)!.trigger('click')
    await flushPromises()

    expect(editPart).toHaveBeenCalledTimes(1)
    expect(saveNoteRegion).not.toHaveBeenCalled()
  })

  it('keeps the note save even if registering the region fails (safe degrade, not a rollback)', async () => {
    vi.mocked(editPart).mockResolvedValue({ part: 'melody', filename: 'melody.mid', url: file.url })
    vi.mocked(saveNoteRegion).mockRejectedValue(new Error('network blip'))
    const wrapper = mountEditable()
    await flushPromises()
    await editBtn(wrapper)!.trigger('click')

    const editor = wrapper.findComponent({ name: 'PianoRollEditor' })
    editor.vm.$emit('region-captured', { startSec: 0, endSec: 2, notes: [{ midi: 67, time: 0, duration: 0.5, velocity: 0.8, isPercussion: false }] })
    editor.vm.$emit('notes-changed', midi.notes, true)
    await flushPromises()

    await saveBtn(wrapper)!.trigger('click')
    await flushPromises()

    expect(editPart).toHaveBeenCalledTimes(1)   // the note edit itself still succeeded
    expect(vi.mocked(logError).mock.calls.some(c => c[0] === 'Save note region')).toBe(true)
    expect(wrapper.emitted('region-saved')).toBeFalsy()
  })

  it('discards a pending take if the editor is closed without saving', async () => {
    vi.mocked(editPart).mockResolvedValue({ part: 'melody', filename: 'melody.mid', url: file.url })
    const wrapper = mountEditable()
    await flushPromises()
    await editBtn(wrapper)!.trigger('click')

    let editor = wrapper.findComponent({ name: 'PianoRollEditor' })
    editor.vm.$emit('region-captured', { startSec: 0, endSec: 2, notes: [{ midi: 67, time: 0, duration: 0.5, velocity: 0.8, isPercussion: false }] })
    editor.vm.$emit('notes-changed', midi.notes, true)
    editor.vm.$emit('close')   // discard the take instead of saving
    await flushPromises()

    // Reopen and save an unrelated plain edit — the earlier take must not leak through.
    await editBtn(wrapper)!.trigger('click')
    editor = wrapper.findComponent({ name: 'PianoRollEditor' })
    editor.vm.$emit('notes-changed', midi.notes, true)
    await flushPromises()
    await saveBtn(wrapper)!.trigger('click')
    await flushPromises()

    expect(saveNoteRegion).not.toHaveBeenCalled()
  })
})
