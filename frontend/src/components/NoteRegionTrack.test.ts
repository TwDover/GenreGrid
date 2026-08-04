/*
 * GenreGrid — a style-based MIDI generator.
 * Copyright (C) 2026 Tw Dover
 *
 * This program is free software: you can redistribute it and/or modify it under
 * the terms of the GNU General Public License v3 or (at your option) any later
 * version. Distributed WITHOUT ANY WARRANTY. See <https://www.gnu.org/licenses/>.
 */
import { describe, it, expect } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import NoteRegionTrack from './NoteRegionTrack.vue'
import type { NoteRegionInfo } from '../types/midi'

const region = (over: Partial<NoteRegionInfo> = {}): NoteRegionInfo => ({
  id: 'r1', part: 'melody', start_bar: 4, bars: 4, loop_count: 1,
  notes: [{ pitch: 60, start: 0, duration: 1, velocity: 100 }],
  ...over,
})

function mountTrack(regions: NoteRegionInfo[], totalBars = 40, disabled = false) {
  const wrapper = mount(NoteRegionTrack, {
    props: { label: 'melody', regions, totalBars, disabled },
    attachTo: document.body,
  })
  const row = wrapper.find('.nr-row').element as HTMLDivElement
  row.getBoundingClientRect = () =>
    ({ left: 0, top: 0, right: 400, bottom: 26, width: 400, height: 26, x: 0, y: 0, toJSON() {} }) as DOMRect
  return wrapper
}

describe('NoteRegionTrack — layout', () => {
  it('positions a block by start_bar/bars as a percent of the total timeline', () => {
    const wrapper = mountTrack([region({ start_bar: 4, bars: 4 })], 40)
    const block = wrapper.find('.nr-block')
    expect(block.attributes('style')).toContain('left: 10%')   // 4/40
    expect(block.attributes('style')).toContain('width: 10%')  // 4/40
  })

  it('widens the block to cover every loop repeat', () => {
    const wrapper = mountTrack([region({ start_bar: 0, bars: 4, loop_count: 3 })], 40)
    const block = wrapper.find('.nr-block')
    expect(block.attributes('style')).toContain('width: 30%')  // 4*3/40
  })
})

describe('NoteRegionTrack — drag to move', () => {
  it('emits move with the bar delta on mouseup, rounded to whole bars', async () => {
    const wrapper = mountTrack([region({ start_bar: 4, bars: 4 })], 40)   // pxPerBar = 400/40 = 10
    const block = wrapper.find('.nr-block')
    await block.trigger('mousedown', { clientX: 100 })
    window.dispatchEvent(new MouseEvent('mousemove', { clientX: 145 }))   // +45px = +4.5 bars -> +5 (round)
    window.dispatchEvent(new MouseEvent('mouseup', { clientX: 145 }))
    await wrapper.vm.$nextTick()

    expect(wrapper.emitted('move')).toBeTruthy()
    expect(wrapper.emitted('move')![0]).toEqual(['r1', 9])   // 4 + 5
  })

  it('clamps a drag past the end of the song', async () => {
    const wrapper = mountTrack([region({ start_bar: 20, bars: 4 })], 40)   // pxPerBar = 10
    const block = wrapper.find('.nr-block')
    await block.trigger('mousedown', { clientX: 100 })
    window.dispatchEvent(new MouseEvent('mousemove', { clientX: 300 }))   // +20 bars, way past the end
    window.dispatchEvent(new MouseEvent('mouseup', { clientX: 300 }))
    await wrapper.vm.$nextTick()

    expect(wrapper.emitted('move')![0]).toEqual(['r1', 36])   // clamped: 36+4=40, the last legal spot
  })

  it('does not emit move when the drag ends back at the start (no-op drag)', async () => {
    const wrapper = mountTrack([region({ start_bar: 4, bars: 4 })])
    const block = wrapper.find('.nr-block')
    await block.trigger('mousedown', { clientX: 100 })
    window.dispatchEvent(new MouseEvent('mousemove', { clientX: 102 }))   // +0.2 bars -> rounds to 0
    window.dispatchEvent(new MouseEvent('mouseup', { clientX: 102 }))
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('move')).toBeFalsy()
  })

  it('ignores drag start while disabled', async () => {
    const wrapper = mountTrack([region({ start_bar: 4, bars: 4 })], 40, true)
    const block = wrapper.find('.nr-block')
    await block.trigger('mousedown', { clientX: 100 })
    window.dispatchEvent(new MouseEvent('mousemove', { clientX: 200 }))
    window.dispatchEvent(new MouseEvent('mouseup', { clientX: 200 }))
    expect(wrapper.emitted('move')).toBeFalsy()
  })
})

describe('NoteRegionTrack — loop stepper + delete', () => {
  const btn = (w: VueWrapper, title: string) => w.findAll('button').find(b => b.attributes('title') === title)!

  it('increments and decrements the loop count, clamped to [1, 32]', async () => {
    const wrapper = mountTrack([region({ loop_count: 1 })])
    await btn(wrapper, 'Fewer repeats').trigger('click')   // already at the floor
    expect(wrapper.emitted('set-loop')).toBeFalsy()
    await btn(wrapper, 'More repeats').trigger('click')
    expect(wrapper.emitted('set-loop')![0]).toEqual(['r1', 2])
  })

  it('emits delete for the clicked region', async () => {
    const wrapper = mountTrack([region()])
    await btn(wrapper, 'Delete this region').trigger('click')
    expect(wrapper.emitted('delete')![0]).toEqual(['r1'])
  })

  it('disables loop/delete controls while disabled', () => {
    const wrapper = mountTrack([region()], 40, true)
    expect((btn(wrapper, 'More repeats').element as HTMLButtonElement).disabled).toBe(true)
    expect((btn(wrapper, 'Delete this region').element as HTMLButtonElement).disabled).toBe(true)
  })
})
