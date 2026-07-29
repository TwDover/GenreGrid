/*
 * GenreGrid — a style-based MIDI generator.
 * Copyright (C) 2026 Tw Dover
 *
 * This program is free software: you can redistribute it and/or modify it under
 * the terms of the GNU General Public License v3 or (at your option) any later
 * version. Distributed WITHOUT ANY WARRANTY. See <https://www.gnu.org/licenses/>.
 */
import { describe, it, expect, beforeAll } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import PianoRoll from './PianoRoll.vue'
import type { ParsedNote } from '../composables/useMidiPlayer'

beforeAll(() => {
  // PianoRoll observes its canvas; jsdom has no ResizeObserver.
  ;(globalThis as unknown as { ResizeObserver?: unknown }).ResizeObserver ??=
    class { observe() {} unobserve() {} disconnect() {} }
})

const melodic = (midi: number, time: number, duration = 0.5): ParsedNote =>
  ({ midi, time, duration, velocity: 0.7, isPercussion: false })

// jsdom gives a zero-size canvas with no getContext; stub a real geometry so the
// pixel↔note math has something to work with. 200×100 buffer, 4s / (58..66) view.
function stubCanvas(wrapper: VueWrapper, w = 200, h = 100) {
  const el = wrapper.find('canvas').element as HTMLCanvasElement
  el.width = w
  el.height = h
  el.getBoundingClientRect = () =>
    ({ left: 0, top: 0, right: w, bottom: h, width: w, height: h, x: 0, y: 0, toJSON() {} }) as DOMRect
  return el
}

const mountRoll = (notes: ParsedNote[]) =>
  mount(PianoRoll, { props: { notes, duration: 4, playing: false, editable: true, secondsPerBeat: 0.5 } })

const lastEmit = (wrapper: VueWrapper) => {
  const e = wrapper.emitted('notes-changed')
  return e ? e[e.length - 1] as [ParsedNote[], boolean] : null
}

describe('PianoRoll drag-to-insert', () => {
  it('inserts a snapped melodic note on a click in empty space', async () => {
    const wrapper = mountRoll([melodic(60, 0), melodic(64, 0)])
    stubCanvas(wrapper)
    // x=100 → 2.0s (snaps to 2.0); y=50 → midi 61 (range 58..66 over 100px)
    await wrapper.find('canvas').trigger('mousedown', { clientX: 100, clientY: 50 })
    window.dispatchEvent(new MouseEvent('mouseup', { clientX: 100, clientY: 50 }))

    const emit = lastEmit(wrapper)
    expect(emit).toBeTruthy()
    const [notes, dirty] = emit!
    expect(dirty).toBe(true)
    expect(notes.length).toBe(3)
    const added = notes[2]
    expect(added.time).toBeCloseTo(2.0)
    expect(added.midi).toBe(61)
    expect(added.duration).toBeCloseTo(0.125)   // one grid (16th @ 120bpm)
    expect(added.isPercussion).toBe(false)
  })

  it('sizes the note by dragging before release', async () => {
    const wrapper = mountRoll([melodic(60, 0), melodic(64, 0)])
    stubCanvas(wrapper)
    await wrapper.find('canvas').trigger('mousedown', { clientX: 100, clientY: 50 })  // 2.0s
    window.dispatchEvent(new MouseEvent('mousemove', { clientX: 150, clientY: 50 }))  // → 3.0s
    window.dispatchEvent(new MouseEvent('mouseup', { clientX: 150, clientY: 50 }))
    const inserted = lastEmit(wrapper)![0]
    const added = inserted[inserted.length - 1]
    expect(added.time).toBeCloseTo(2.0)
    expect(added.duration).toBeCloseTo(1.0)
  })

  it('selects (does not insert) when pressing on an existing note', async () => {
    const wrapper = mountRoll([melodic(60, 0)])
    stubCanvas(wrapper)
    // single note midi 60 → view 58..62; its row top y=25, x 0..24. Press inside it.
    await wrapper.find('canvas').trigger('mousedown', { clientX: 5, clientY: 28 })
    window.dispatchEvent(new MouseEvent('mouseup', { clientX: 5, clientY: 28 }))
    expect(wrapper.emitted('notes-changed')).toBeFalsy()  // selection emits nothing
  })

  it('does not insert on a percussion (drum) part', async () => {
    const wrapper = mountRoll([{ midi: 36, time: 0, duration: 0.1, velocity: 0.8, isPercussion: true }])
    stubCanvas(wrapper)
    await wrapper.find('canvas').trigger('mousedown', { clientX: 100, clientY: 50 })
    window.dispatchEvent(new MouseEvent('mouseup', { clientX: 100, clientY: 50 }))
    expect(wrapper.emitted('notes-changed')).toBeFalsy()
  })
})

describe('PianoRoll edge-grab resize', () => {
  // A note at t=1.0 dur=1.0 midi=60 → drawn x∈[50,99], y-row ≈25..46 (200×100, 4s, 58..62).
  const noteAtEdge = () => [melodic(60, 1.0, 1.0)]

  it('drags the right edge to lengthen the note', async () => {
    const wrapper = mountRoll(noteAtEdge())
    stubCanvas(wrapper)
    await wrapper.find('canvas').trigger('mousedown', { clientX: 97, clientY: 30 })  // grab right edge
    window.dispatchEvent(new MouseEvent('mousemove', { clientX: 180, clientY: 30 })) // drag to ~3.6s
    window.dispatchEvent(new MouseEvent('mouseup', { clientX: 180, clientY: 30 }))
    const [notes, dirty] = lastEmit(wrapper)!
    expect(dirty).toBe(true)
    expect(notes).toHaveLength(1)
    expect(notes[0].time).toBeCloseTo(1.0)          // start stays put
    expect(notes[0].duration).toBeCloseTo(2.625)    // end snapped to 3.625 - 1.0
  })

  it('pressing the note body selects (does not resize/insert)', async () => {
    const wrapper = mountRoll(noteAtEdge())
    stubCanvas(wrapper)
    await wrapper.find('canvas').trigger('mousedown', { clientX: 60, clientY: 30 })  // mid-body
    window.dispatchEvent(new MouseEvent('mouseup', { clientX: 60, clientY: 30 }))
    expect(wrapper.emitted('notes-changed')).toBeFalsy()
  })

  it('shows a resize cursor only over the right edge', async () => {
    const wrapper = mountRoll(noteAtEdge())
    const el = stubCanvas(wrapper)
    await wrapper.find('canvas').trigger('mousemove', { clientX: 97, clientY: 30 })  // over edge
    expect(el.style.cursor).toBe('ew-resize')
    await wrapper.find('canvas').trigger('mousemove', { clientX: 60, clientY: 30 })  // over body
    expect(el.style.cursor).toBe('')
  })
})
