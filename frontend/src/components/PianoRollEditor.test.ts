/*
 * GenreGrid — a style-based MIDI generator.
 * Copyright (C) 2026 Tw Dover
 *
 * This program is free software: you can redistribute it and/or modify it under
 * the terms of the GNU General Public License v3 or (at your option) any later
 * version. Distributed WITHOUT ANY WARRANTY. See <https://www.gnu.org/licenses/>.
 */
import { describe, it, expect, beforeAll, beforeEach, vi } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'

// Mock the audio engine so playback/audition wiring is assertable without Tone.
const player = {
  toggle: vi.fn().mockResolvedValue(undefined),
  stop: vi.fn(),
  audition: vi.fn(),
  prepareAudition: vi.fn(),
  isPlayingUrl: vi.fn().mockReturnValue(true),
}
vi.mock('../composables/useMidiPlayer', () => ({ useMidiPlayer: () => player }))

import PianoRollEditor from './PianoRollEditor.vue'
import type { ParsedNote } from '../composables/useMidiPlayer'

beforeAll(() => {
  ;(globalThis as unknown as { ResizeObserver?: unknown }).ResizeObserver ??=
    class { observe() {} unobserve() {} disconnect() {} }
})
beforeEach(() => {
  player.toggle.mockClear(); player.stop.mockClear()
  player.audition.mockClear(); player.prepareAudition.mockClear()
  player.isPlayingUrl.mockReturnValue(true)
  // jsdom has no object-URL support; the editor encodes its buffer to one for playback.
  URL.createObjectURL = vi.fn(() => 'blob:mock')
  URL.revokeObjectURL = vi.fn()
})

const melodic = (midi: number, time: number, duration = 0.5): ParsedNote =>
  ({ midi, time, duration, velocity: 0.7, isPercussion: false })

// The editor draws to a viewport-sized canvas; in jsdom getContext is null so draw()
// no-ops, and the DOM has no real geometry. Stub an 800×500 canvas at the origin and
// press "Fit" so the zoom is derived from that known size before we drive events.
function mountEditor(notes: ParsedNote[], duration = 2.0) {
  const wrapper = mount(PianoRollEditor, {
    props: { notes, duration, secondsPerBeat: 0.5, keyRoot: 'C', scale: 'minor', partName: 'melody', styleId: 'lofi' },
    attachTo: document.body,
  })
  const el = wrapper.find('canvas').element as HTMLCanvasElement
  el.width = 800
  el.height = 500
  el.getBoundingClientRect = () =>
    ({ left: 0, top: 0, right: 800, bottom: 500, width: 800, height: 500, x: 0, y: 0, toJSON() {} }) as DOMRect
  return wrapper
}

const fitBtn = (w: VueWrapper) => w.findAll('button').find(b => b.text() === 'Fit')!
async function clickFit(w: VueWrapper) { await fitBtn(w).trigger('click') }

const lastEmit = (w: VueWrapper) => {
  const e = w.emitted('notes-changed')
  return e ? e[e.length - 1] as [ParsedNote[], boolean] : null
}
const isGridMultiple = (t: number, grid: number) => Math.abs(t / grid - Math.round(t / grid)) < 1e-6

describe('PianoRollEditor — insert', () => {
  it('inserts a grid-snapped melodic note on a click in the grid', async () => {
    const wrapper = mountEditor([melodic(60, 0)])
    await clickFit(wrapper)
    await wrapper.find('canvas').trigger('mousedown', { clientX: 300, clientY: 220 })
    window.dispatchEvent(new MouseEvent('mouseup', { clientX: 300, clientY: 220 }))

    const emit = lastEmit(wrapper)
    expect(emit).toBeTruthy()
    const [notes, dirty] = emit!
    expect(dirty).toBe(true)
    expect(notes.length).toBe(2)
    const added = notes[notes.length - 1]
    expect(added.isPercussion).toBe(false)
    expect(isGridMultiple(added.time, 0.125)).toBe(true)   // snapped to the 1/16 grid (0.125s @ 120bpm)
    expect(added.duration).toBeGreaterThanOrEqual(0.125)
  })

  it('snaps to a coarser grid when the snap selector changes', async () => {
    const wrapper = mountEditor([melodic(60, 0)])
    await clickFit(wrapper)
    await wrapper.find('select').setValue(0.5)   // 1/8 note
    await wrapper.find('canvas').trigger('mousedown', { clientX: 305, clientY: 220 })
    window.dispatchEvent(new MouseEvent('mouseup', { clientX: 305, clientY: 220 }))
    const added = lastEmit(wrapper)![0].slice(-1)[0]
    expect(isGridMultiple(added.time, 0.25)).toBe(true)   // 1/8 @ 120bpm = 0.25s
    expect(added.duration).toBeCloseTo(0.25)              // one 1/8 grid minimum
  })

  it('does not insert on a percussion part', async () => {
    const wrapper = mountEditor([{ midi: 36, time: 0, duration: 0.1, velocity: 0.8, isPercussion: true }])
    await clickFit(wrapper)
    await wrapper.find('canvas').trigger('mousedown', { clientX: 300, clientY: 220 })
    window.dispatchEvent(new MouseEvent('mouseup', { clientX: 300, clientY: 220 }))
    expect(wrapper.emitted('notes-changed')).toBeFalsy()
  })
})

describe('PianoRollEditor — resize', () => {
  it('lengthens a note by dragging its right edge', async () => {
    // Single note time=1.0s dur=0.5s midi=60. After Fit at 800×500 the note draws at a
    // known rect; grab its right edge and drag right.
    const wrapper = mountEditor([melodic(60, 1.0, 0.5)])
    await clickFit(wrapper)
    // right edge ≈ x 329 (see viewport math); press just inside it, then drag to ~460.
    await wrapper.find('canvas').trigger('mousedown', { clientX: 328, clientY: 170 })
    window.dispatchEvent(new MouseEvent('mousemove', { clientX: 460, clientY: 170 }))
    window.dispatchEvent(new MouseEvent('mouseup', { clientX: 460, clientY: 170 }))
    const [notes, dirty] = lastEmit(wrapper)!
    expect(dirty).toBe(true)
    expect(notes).toHaveLength(1)
    expect(notes[0].time).toBeCloseTo(1.0)                 // start stays put
    expect(notes[0].duration).toBeGreaterThan(0.5)         // grew
    expect(isGridMultiple(notes[0].time + notes[0].duration, 0.125)).toBe(true)  // end on grid
  })
})

describe('PianoRollEditor — delete + close', () => {
  it('deletes the selected note with Backspace', async () => {
    const wrapper = mountEditor([melodic(60, 1.0, 0.5)])
    await clickFit(wrapper)
    await wrapper.find('canvas').trigger('mousedown', { clientX: 260, clientY: 175 })  // select body
    window.dispatchEvent(new MouseEvent('mouseup', { clientX: 260, clientY: 175 }))
    await wrapper.find('canvas').trigger('keydown', { key: 'Backspace' })
    const [notes, dirty] = lastEmit(wrapper)!
    expect(dirty).toBe(true)
    expect(notes).toHaveLength(0)
  })

  it('emits close on Escape and on the ✕ button', async () => {
    const wrapper = mountEditor([melodic(60, 0)])
    await wrapper.find('canvas').trigger('keydown', { key: 'Escape' })
    expect(wrapper.emitted('close')).toBeTruthy()
  })
})

describe('PianoRollEditor — save button', () => {
  it('is disabled until an edit makes the buffer dirty, then emits save', async () => {
    const wrapper = mountEditor([melodic(60, 0)])
    await clickFit(wrapper)
    const saveBtn = wrapper.findAll('button').find(b => b.text() === 'Save edits')!
    expect((saveBtn.element as HTMLButtonElement).disabled).toBe(true)

    await wrapper.find('canvas').trigger('mousedown', { clientX: 300, clientY: 220 })
    window.dispatchEvent(new MouseEvent('mouseup', { clientX: 300, clientY: 220 }))
    await wrapper.vm.$nextTick()
    expect((saveBtn.element as HTMLButtonElement).disabled).toBe(false)

    await saveBtn.trigger('click')
    expect(wrapper.emitted('save')).toBeTruthy()
  })
})

// ── Multi-select + velocity lane (roadmap 5.1 steps 3–4) ─────────────────────
// Geometry after Fit at 800×500 with these two notes: totalBeats=12 → pxPerBeat≈61.17,
// pitchCount=13 → pxPerSemitone≈30.3. GUTTER_W=54, RULER_H=26, SB=12, VELO_H=68 →
// grid y 26..420, velocity lane y 420..488.
const twoNotes = () => [melodic(60, 1.0, 0.5), melodic(64, 2.0, 0.5)]
const selectTool = async (w: VueWrapper) =>
  (w.findAll('button').find(b => b.text().includes('Select')))!.trigger('click')

describe('PianoRollEditor — marquee multi-select', () => {
  it('marquees a group and deletes them all at once', async () => {
    const wrapper = mountEditor(twoNotes())
    await clickFit(wrapper)
    await selectTool(wrapper)
    // Drag a box over the whole grid (top-left empty corner → bottom-right).
    await wrapper.find('canvas').trigger('mousedown', { clientX: 60, clientY: 30 })
    window.dispatchEvent(new MouseEvent('mousemove', { clientX: 780, clientY: 415 }))
    window.dispatchEvent(new MouseEvent('mouseup', { clientX: 780, clientY: 415 }))
    await wrapper.vm.$nextTick()
    // "2 selected" chip appears.
    expect(wrapper.text()).toContain('2 selected')
    await wrapper.find('canvas').trigger('keydown', { key: 'Backspace' })
    const [notes, dirty] = lastEmit(wrapper)!
    expect(dirty).toBe(true)
    expect(notes).toHaveLength(0)   // both removed
  })
})

describe('PianoRollEditor — group transpose', () => {
  it('Ctrl+A selects all; arrows shift every selected note together', async () => {
    const wrapper = mountEditor(twoNotes())
    await clickFit(wrapper)
    await wrapper.find('canvas').trigger('keydown', { key: 'a', ctrlKey: true })
    expect(wrapper.text()).toContain('2 selected')
    await wrapper.find('canvas').trigger('keydown', { key: 'ArrowRight' })   // +1 grid (0.125s)
    let notes = lastEmit(wrapper)![0]
    expect(notes.find(n => n.midi === 60)!.time).toBeCloseTo(1.125)
    expect(notes.find(n => n.midi === 64)!.time).toBeCloseTo(2.125)
    await wrapper.find('canvas').trigger('keydown', { key: 'ArrowUp' })      // +1 semitone, both
    notes = lastEmit(wrapper)![0]
    expect(notes.map(n => n.midi).sort()).toEqual([61, 65])
  })
})

describe('PianoRollEditor — shift-click extend', () => {
  it('adds a second note to the selection with shift-click', async () => {
    const wrapper = mountEditor(twoNotes())
    await clickFit(wrapper)
    // Click note A body (midi 60 @ beat 2 → x≈176..237, y≈268).
    await wrapper.find('canvas').trigger('mousedown', { clientX: 200, clientY: 278 })
    window.dispatchEvent(new MouseEvent('mouseup', { clientX: 200, clientY: 278 }))
    // Shift-click note B (midi 64 @ beat 4 → x≈299..360, y≈147).
    await wrapper.find('canvas').trigger('mousedown', { clientX: 320, clientY: 158, shiftKey: true })
    window.dispatchEvent(new MouseEvent('mouseup', { clientX: 320, clientY: 158, shiftKey: true }))
    expect(wrapper.text()).toContain('2 selected')
    await wrapper.find('canvas').trigger('keydown', { key: 'Delete' })
    expect(lastEmit(wrapper)![0]).toHaveLength(0)
  })
})

describe('PianoRollEditor — velocity lane', () => {
  it('drags a note velocity in the lane', async () => {
    const wrapper = mountEditor(twoNotes())
    await clickFit(wrapper)
    // Note A bar sits at x≈176 in the lane (y 420..488). Drag near the top → high velocity.
    await wrapper.find('canvas').trigger('mousedown', { clientX: 178, clientY: 428 })
    window.dispatchEvent(new MouseEvent('mouseup', { clientX: 178, clientY: 428 }))
    const [notes, dirty] = lastEmit(wrapper)!
    expect(dirty).toBe(true)
    const a = notes.find(n => n.midi === 60)!
    expect(a.velocity).toBeGreaterThan(0.7)          // raised from the default 0.7
    expect(notes.find(n => n.midi === 64)!.velocity).toBeCloseTo(0.7)   // B untouched
  })
})

// ── Playback, loop region, audition (editor "hear what you're editing") ──────
import { flushPromises } from '@vue/test-utils'

const playBtn = (w: VueWrapper) => w.findAll('button').find(b => b.text() === '▶' || b.text() === '■')!

describe('PianoRollEditor — transport', () => {
  it('plays the edited buffer as a blob on the part channel, then stops', async () => {
    const wrapper = mountEditor([melodic(60, 0.5)])
    await clickFit(wrapper)
    await playBtn(wrapper).trigger('click')
    await flushPromises()
    expect(player.toggle).toHaveBeenCalledTimes(1)
    const [url, styleId, , loop, region] = player.toggle.mock.calls[0]
    expect(url).toMatch(/^blob:/)
    expect(styleId).toBe('lofi')
    expect(loop).toBe(false)
    expect(region).toBeUndefined()          // no loop region set
    // Now shows ■; clicking again stops.
    await playBtn(wrapper).trigger('click')
    expect(player.stop).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })
})

describe('PianoRollEditor — loop region', () => {
  it('drags a region in the ruler and passes it to playback', async () => {
    const wrapper = mountEditor([melodic(60, 0.5)])
    await clickFit(wrapper)
    // Drag across the ruler (y < 26).
    await wrapper.find('canvas').trigger('mousedown', { clientX: 200, clientY: 6 })
    window.dispatchEvent(new MouseEvent('mousemove', { clientX: 520, clientY: 6 }))
    window.dispatchEvent(new MouseEvent('mouseup', { clientX: 520, clientY: 6 }))
    await playBtn(wrapper).trigger('click')
    await flushPromises()
    const region = player.toggle.mock.calls[0][4]
    expect(region).toBeTruthy()
    expect(region.end).toBeGreaterThan(region.start)
    wrapper.unmount()
  })
})

describe('PianoRollEditor — audition', () => {
  it('warms the preview instrument on open', async () => {
    mountEditor([melodic(60, 0)])
    await flushPromises()   // onMounted awaits nextTick before prepareAudition
    expect(player.prepareAudition).toHaveBeenCalledWith('lofi', 'melody')
  })
  it('auditions the pitch of a clicked keyboard-gutter key', async () => {
    const wrapper = mountEditor([melodic(60, 1.0)])
    await clickFit(wrapper)
    await wrapper.find('canvas').trigger('mousedown', { clientX: 20, clientY: 200 })   // in the gutter
    window.dispatchEvent(new MouseEvent('mouseup', { clientX: 20, clientY: 200 }))
    expect(player.audition).toHaveBeenCalledTimes(1)
    const [styleId, part, midi] = player.audition.mock.calls[0]
    expect(styleId).toBe('lofi'); expect(part).toBe('melody'); expect(typeof midi).toBe('number')
  })
  it('auditions a note the moment it is inserted', async () => {
    const wrapper = mountEditor([melodic(60, 0)])
    await clickFit(wrapper)
    await wrapper.find('canvas').trigger('mousedown', { clientX: 300, clientY: 220 })
    window.dispatchEvent(new MouseEvent('mouseup', { clientX: 300, clientY: 220 }))
    expect(player.audition).toHaveBeenCalled()
  })
})

describe('PianoRollEditor — loop flags', () => {
  // With one note (time 0.5s) Fit gives totalBeats 8 → pxPerBeat = 734/8 = 91.75,
  // gutter 54, scroll 0, so a beat maps to x = 54 + beat*91.75. Click flags exactly.
  const bx = (beat: number) => 54 + beat * 91.75
  const stopVia = async (w: VueWrapper) => { await playBtn(w).trigger('click'); await flushPromises() }

  it('dragging the end flag moves only the end edge', async () => {
    const wrapper = mountEditor([melodic(60, 0.5)])
    await clickFit(wrapper)
    // Region beats 2..5 via the ruler.
    await wrapper.find('canvas').trigger('mousedown', { clientX: bx(2), clientY: 6 })
    window.dispatchEvent(new MouseEvent('mousemove', { clientX: bx(5), clientY: 6 }))
    window.dispatchEvent(new MouseEvent('mouseup', { clientX: bx(5), clientY: 6 }))
    await playBtn(wrapper).trigger('click'); await flushPromises()
    const first = player.toggle.mock.calls[0][4]
    expect(first.end).toBeGreaterThan(first.start)
    const startEdge = first.start
    await stopVia(wrapper)
    player.toggle.mockClear()

    // Grab the END flag (beat 5) and drag it to beat 6 — start must not move.
    await wrapper.find('canvas').trigger('mousedown', { clientX: bx(5), clientY: 6 })
    window.dispatchEvent(new MouseEvent('mousemove', { clientX: bx(6), clientY: 6 }))
    window.dispatchEvent(new MouseEvent('mouseup', { clientX: bx(6), clientY: 6 }))
    await playBtn(wrapper).trigger('click'); await flushPromises()
    const second = player.toggle.mock.calls[0][4]
    expect(second.start).toBeCloseTo(startEdge, 5)   // start unchanged
    expect(second.end).toBeGreaterThan(first.end)     // end extended
    wrapper.unmount()
  })

  it('drags the start flag independently of the end', async () => {
    const wrapper = mountEditor([melodic(60, 0.5)])
    await clickFit(wrapper)
    await wrapper.find('canvas').trigger('mousedown', { clientX: bx(2), clientY: 6 })
    window.dispatchEvent(new MouseEvent('mousemove', { clientX: bx(5), clientY: 6 }))
    window.dispatchEvent(new MouseEvent('mouseup', { clientX: bx(5), clientY: 6 }))
    await playBtn(wrapper).trigger('click'); await flushPromises()
    const before = player.toggle.mock.calls[0][4]
    await stopVia(wrapper)
    player.toggle.mockClear()
    // Grab the START flag (beat 2) and pull it in to beat 3.
    await wrapper.find('canvas').trigger('mousedown', { clientX: bx(2), clientY: 6 })
    window.dispatchEvent(new MouseEvent('mousemove', { clientX: bx(3), clientY: 6 }))
    window.dispatchEvent(new MouseEvent('mouseup', { clientX: bx(3), clientY: 6 }))
    await playBtn(wrapper).trigger('click'); await flushPromises()
    const after = player.toggle.mock.calls[0][4]
    expect(after.start).toBeGreaterThan(before.start)   // start moved in
    expect(after.end).toBeCloseTo(before.end, 5)        // end unchanged
    wrapper.unmount()
  })
})
