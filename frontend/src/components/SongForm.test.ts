/*
 * GenreGrid — a style-based MIDI generator.
 * Copyright (C) 2026 Tw Dover
 *
 * This program is free software: you can redistribute it and/or modify it under
 * the terms of the GNU General Public License v3 or (at your option) any later
 * version. Distributed WITHOUT ANY WARRANTY. See <https://www.gnu.org/licenses/>.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'

// Mock the API so we assert what the form sends without a backend (roadmap-2 5.4).
const buildSong = vi.fn()
const buildSongFromMelody = vi.fn()
const buildSongFromGroove = vi.fn()
vi.mock('../services/api', () => ({
  buildSong: (...a: unknown[]) => buildSong(...a),
  buildSongFromMelody: (...a: unknown[]) => buildSongFromMelody(...a),
  buildSongFromGroove: (...a: unknown[]) => buildSongFromGroove(...a),
}))

import SongForm from './SongForm.vue'
import type { StyleInfo } from '../types/midi'

const styles: StyleInfo[] = [
  { id: 'lofi', name: 'Lofi', bpm_range: [70, 100], default_scale: 'minor', has_prior: false },
]

const fakeResponse = { generation_id: 'x', style: 'lofi', files: [], seed: 1, template: 'verse_chorus', total_bars: 8, sections: [], bpm: 90, key: 'C minor', progression: [] }

beforeEach(() => {
  buildSong.mockReset().mockResolvedValue(fakeResponse)
  buildSongFromMelody.mockReset().mockResolvedValue(fakeResponse)
  buildSongFromGroove.mockReset().mockResolvedValue(fakeResponse)
})

const mountForm = () => mount(SongForm, { props: { styles } })

function setFile(wrapper: VueWrapper, index: number, name = 'x.mid') {
  const input = wrapper.findAll('input[type="file"]')[index].element as HTMLInputElement
  const file = new File([new Uint8Array([1, 2, 3])], name, { type: 'audio/midi' })
  Object.defineProperty(input, 'files', { value: [file], configurable: true })
  return wrapper.findAll('input[type="file"]')[index].trigger('change')
}

const build = (wrapper: VueWrapper) => wrapper.find('.sb-generate-btn').trigger('click')

describe('SongForm — seed from progression / groove (5.4)', () => {
  it('passes a typed progression to buildSong as progression_text', async () => {
    const wrapper = mountForm()
    await wrapper.find('.prog-input').setValue('Am F C G')
    await build(wrapper)
    await flushPromises()
    expect(buildSong).toHaveBeenCalledTimes(1)
    expect(buildSong.mock.calls[0][0]).toMatchObject({ progression_text: 'Am F C G' })
    expect(buildSongFromGroove).not.toHaveBeenCalled()
  })

  it('omits progression_text when the box is empty', async () => {
    const wrapper = mountForm()
    await build(wrapper)
    await flushPromises()
    expect(buildSong.mock.calls[0][0]).not.toHaveProperty('progression_text')
  })

  it('routes a selected groove file to buildSongFromGroove', async () => {
    const wrapper = mountForm()
    await setFile(wrapper, 1, 'groove.mid')      // second file input = groove
    await build(wrapper)
    await flushPromises()
    expect(buildSongFromGroove).toHaveBeenCalledTimes(1)
    expect(buildSong).not.toHaveBeenCalled()
  })

  it('carries a typed progression through the groove path', async () => {
    const wrapper = mountForm()
    await wrapper.find('.prog-input').setValue('i VI iv v')
    await setFile(wrapper, 1, 'groove.mid')
    await build(wrapper)
    await flushPromises()
    expect(buildSongFromGroove.mock.calls[0][1]).toMatchObject({ progression_text: 'i VI iv v' })
  })

  it('melody upload wins over a groove upload', async () => {
    const wrapper = mountForm()
    await setFile(wrapper, 0, 'melody.mid')      // first file input = melody
    await setFile(wrapper, 1, 'groove.mid')
    await build(wrapper)
    await flushPromises()
    expect(buildSongFromMelody).toHaveBeenCalledTimes(1)
    expect(buildSongFromGroove).not.toHaveBeenCalled()
  })

  it('disables the progression box while a melody file is selected', async () => {
    const wrapper = mountForm()
    await setFile(wrapper, 0, 'melody.mid')
    expect((wrapper.find('.prog-input').element as HTMLInputElement).disabled).toBe(true)
  })
})
