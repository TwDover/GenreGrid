/*
 * GenreGrid — a style-based MIDI generator.
 * Copyright (C) 2026 Tw Dover
 *
 * This program is free software: you can redistribute it and/or modify it under
 * the terms of the GNU General Public License v3 or (at your option) any later
 * version. Distributed WITHOUT ANY WARRANTY. See <https://www.gnu.org/licenses/>.
 */
import { describe, it, expect, beforeAll, beforeEach, vi } from 'vitest'
import { ref } from 'vue'
import { mount, type VueWrapper } from '@vue/test-utils'

// Mock the audio engine so playback/audition wiring is assertable without Tone.
// The live-tempo bits are real refs so the shared control renders in the toolbar.
const playbackBpm = ref(120)
const isTempoNudged = ref(false)
const player = {
  toggle: vi.fn().mockResolvedValue(undefined),
  stop: vi.fn(),
  audition: vi.fn(),
  scheduleAudition: vi.fn(),
  prepareAudition: vi.fn(),
  isPlayingUrl: vi.fn().mockReturnValue(true),
  playbackBpm,
  isTempoNudged,
  tempoRatio: ref(1),
  setPlaybackBpm: vi.fn((b: number) => { playbackBpm.value = b }),
  resetPlaybackBpm: vi.fn(),
}
vi.mock('../composables/useMidiPlayer', () => ({ useMidiPlayer: () => player }))

// Mock live MIDI-in + metronome so recording is drivable without Web MIDI / audio.
// `recNoteCb` captures the recorder's note-stream handler so tests can inject notes.
let recNoteCb: ((ev: { type: 'on' | 'off'; note: number; velocity: number }) => void) | null = null
const midiIn = { supported: true, enabled: ref(false), part: ref('melody'), enable: vi.fn().mockResolvedValue(undefined), setPart: vi.fn() }
vi.mock('../composables/useMidiInput', () => ({
  useMidiInput: () => midiIn,
  onMidiNote: (cb: (ev: { type: 'on' | 'off'; note: number; velocity: number }) => void) => { recNoteCb = cb; return () => { recNoteCb = null } },
  setAuditionTarget: vi.fn(),
  clearAuditionTarget: vi.fn(),
}))
vi.mock('../composables/useMetronome', () => ({
  countIn: vi.fn().mockResolvedValue(0),
  setMeter: vi.fn(),
}))

import PianoRollEditor from './PianoRollEditor.vue'
import type { ParsedNote } from '../composables/useMidiPlayer'

beforeAll(() => {
  ;(globalThis as unknown as { ResizeObserver?: unknown }).ResizeObserver ??=
    class { observe() {} unobserve() {} disconnect() {} }
})
beforeEach(() => {
  player.toggle.mockClear(); player.stop.mockClear()
  player.audition.mockClear(); player.prepareAudition.mockClear()
  player.setPlaybackBpm.mockClear(); player.resetPlaybackBpm.mockClear()
  player.isPlayingUrl.mockReturnValue(true)
  midiIn.enable.mockClear(); midiIn.enabled.value = false
  playbackBpm.value = 120; isTempoNudged.value = false
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

  it('inserts a percussion hit on a drum part (Draw tool)', async () => {
    const wrapper = mountEditor([{ midi: 36, time: 0, duration: 0.1, velocity: 0.8, isPercussion: true }])
    await clickFit(wrapper)
    await wrapper.find('canvas').trigger('mousedown', { clientX: 300, clientY: 220 })
    window.dispatchEvent(new MouseEvent('mouseup', { clientX: 300, clientY: 220 }))
    const [notes, dirty] = lastEmit(wrapper)!
    expect(dirty).toBe(true)
    expect(notes.length).toBe(2)                             // original + drawn hit
    expect(notes[notes.length - 1].isPercussion).toBe(true)  // drawn as a drum hit
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

// ── Volume/Pan automation lane (roadmap 9.3) ──────────────────────────────────
// Same lane geometry as velocity (y 420..488 after Fit) — the lane just draws/
// hit-tests a curve of independent {time, value} points instead of per-note bars.
import type { PartAutomation } from '../composables/useMidiPlayer'

const laneBtn = (w: VueWrapper, label: 'Velocity' | 'Volume' | 'Pan') =>
  w.findAll('button').find(b => b.text() === label)!
const lastAutomationEmit = (w: VueWrapper) => {
  const e = w.emitted('automation-changed')
  return e ? e[e.length - 1] as [PartAutomation, boolean] : null
}

describe('PianoRollEditor — volume/pan automation lane', () => {
  it('clicking empty lane space in Volume mode inserts a breakpoint', async () => {
    const wrapper = mountEditor(twoNotes())
    await clickFit(wrapper)
    await laneBtn(wrapper, 'Volume').trigger('click')
    // Near the lane's top (y 420..488) -> a high value.
    await wrapper.find('canvas').trigger('mousedown', { clientX: 300, clientY: 428 })
    window.dispatchEvent(new MouseEvent('mouseup', { clientX: 300, clientY: 428 }))
    const [automation, dirty] = lastAutomationEmit(wrapper)!
    expect(dirty).toBe(true)
    expect(automation.volume).toHaveLength(1)
    expect(automation.volume[0].value).toBeGreaterThan(0.7)
    expect(automation.pan).toHaveLength(0)   // untouched
  })

  it('dragging an existing point moves it instead of adding a second one', async () => {
    const wrapper = mountEditor(twoNotes())
    await clickFit(wrapper)
    await laneBtn(wrapper, 'Volume').trigger('click')
    await wrapper.find('canvas').trigger('mousedown', { clientX: 300, clientY: 460 })
    window.dispatchEvent(new MouseEvent('mouseup', { clientX: 300, clientY: 460 }))
    const firstValue = lastAutomationEmit(wrapper)![0].volume[0].value

    // Press again on the same point and drag it up (toward the lane top).
    await wrapper.find('canvas').trigger('mousedown', { clientX: 300, clientY: 460 })
    window.dispatchEvent(new MouseEvent('mousemove', { clientX: 300, clientY: 425 }))
    window.dispatchEvent(new MouseEvent('mouseup', { clientX: 300, clientY: 425 }))
    const [automation] = lastAutomationEmit(wrapper)!
    expect(automation.volume).toHaveLength(1)              // moved, not duplicated
    expect(automation.volume[0].value).toBeGreaterThan(firstValue)
  })

  it('double-clicking an existing point removes it', async () => {
    const wrapper = mountEditor(twoNotes())
    await clickFit(wrapper)
    await laneBtn(wrapper, 'Pan').trigger('click')
    await wrapper.find('canvas').trigger('mousedown', { clientX: 300, clientY: 450 })
    window.dispatchEvent(new MouseEvent('mouseup', { clientX: 300, clientY: 450 }))
    expect(lastAutomationEmit(wrapper)![0].pan).toHaveLength(1)

    await wrapper.find('canvas').trigger('dblclick', { clientX: 300, clientY: 450 })
    expect(lastAutomationEmit(wrapper)![0].pan).toHaveLength(0)
  })

  it('Velocity mode is unaffected by drawn automation and vice versa', async () => {
    const wrapper = mountEditor(twoNotes())
    await clickFit(wrapper)
    await laneBtn(wrapper, 'Pan').trigger('click')
    await wrapper.find('canvas').trigger('mousedown', { clientX: 300, clientY: 450 })
    window.dispatchEvent(new MouseEvent('mouseup', { clientX: 300, clientY: 450 }))

    await laneBtn(wrapper, 'Velocity').trigger('click')
    await wrapper.find('canvas').trigger('mousedown', { clientX: 178, clientY: 428 })
    window.dispatchEvent(new MouseEvent('mouseup', { clientX: 178, clientY: 428 }))
    const [notes] = lastEmit(wrapper)!
    expect(notes.find(n => n.midi === 60)!.velocity).toBeGreaterThan(0.7)   // velocity drag still works
    expect(lastAutomationEmit(wrapper)![0].pan).toHaveLength(1)             // pan point survived the mode switch
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

  it('shows the live-tempo control only while playing and nudges it', async () => {
    const wrapper = mountEditor([melodic(60, 0.5)])
    await clickFit(wrapper)
    expect(wrapper.find('.pre-tempo').exists()).toBe(false)   // hidden when idle

    await playBtn(wrapper).trigger('click')
    await flushPromises()
    const tempo = wrapper.find('.pre-tempo')
    expect(tempo.exists()).toBe(true)
    expect(tempo.find('.pre-tempo-val').text()).toContain('120')

    // − / + drive the shared non-destructive tempo (playback only).
    await tempo.find('.pre-tempo-step').trigger('click')       // the first step (−)
    expect(player.setPlaybackBpm).toHaveBeenCalledWith(119)
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
  it('takes control of MIDI input on open so a controller sounds the edited part', async () => {
    mountEditor([melodic(60, 0)])
    await flushPromises()
    expect(midiIn.enable).toHaveBeenCalled()   // auto-engaged — no separate enable step needed
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

describe('PianoRollEditor — MIDI recording', () => {
  const recBtn = (w: VueWrapper) => w.findAll('button').find(b => /rec/i.test(b.text()))!

  it('loop-records played notes (overdub) and commits them on stop', async () => {
    const wrapper = mountEditor([melodic(60, 0.5)])   // one existing note
    await clickFit(wrapper)

    await recBtn(wrapper).trigger('click')     // arm + start recording
    await flushPromises()
    expect(recNoteCb).toBeTypeOf('function')   // recorder subscribed to the note stream
    expect(player.toggle).toHaveBeenCalled()   // looping playback started (with a region)
    expect(player.toggle.mock.calls[0][4]).toBeTruthy()

    // Play two notes (note-on then note-off).
    recNoteCb!({ type: 'on', note: 67, velocity: 0.8 }); recNoteCb!({ type: 'off', note: 67, velocity: 0 })
    recNoteCb!({ type: 'on', note: 72, velocity: 0.6 }); recNoteCb!({ type: 'off', note: 72, velocity: 0 })

    await recBtn(wrapper).trigger('click')     // stop → quantize + commit (unsaved)
    const [notes, dirty] = lastEmit(wrapper)!
    expect(dirty).toBe(true)
    expect(notes).toHaveLength(3)              // original + two overdubbed
    expect(notes.map(n => n.midi)).toEqual(expect.arrayContaining([60, 67, 72]))
    expect(recNoteCb).toBeNull()               // unsubscribed on stop
    // The take is committed as a DIRTY edit, not auto-saved — the user reviews it and
    // hits Save edits (which is now enabled) or undoes it if the take didn't land.
    expect(wrapper.emitted('save')).toBeFalsy()
    expect((wrapper.findAll('button').find(b => b.text() === 'Save edits')!.element as HTMLButtonElement).disabled).toBe(false)
    wrapper.unmount()
  })

  it('records drum pads as percussion hits into the part', async () => {
    const wrapper = mountEditor([{ midi: 36, time: 0, duration: 0.25, velocity: 0.9, isPercussion: true }])
    await clickFit(wrapper)
    const btn = recBtn(wrapper)
    expect(btn).toBeTruthy()   // drums can loop-record too
    await btn.trigger('click')
    await flushPromises()
    recNoteCb!({ type: 'on', note: 38, velocity: 0.8 }); recNoteCb!({ type: 'off', note: 38, velocity: 0 })
    await btn.trigger('click')     // stop → quantize + commit
    const [notes] = lastEmit(wrapper)!
    const added = notes.find(n => n.midi === 38)
    expect(added).toBeTruthy()
    expect(added!.isPercussion).toBe(true)   // captured as a drum hit, not a melodic note
    wrapper.unmount()
  })
})

describe('PianoRollEditor — drum lane', () => {
  const drum = (midi: number, time: number): ParsedNote =>
    ({ midi, time, duration: 0.25, velocity: 0.8, isPercussion: true })
  function mountDrums(notes: ParsedNote[]) {
    const wrapper = mount(PianoRollEditor, {
      props: { notes, duration: 2.0, secondsPerBeat: 0.5, keyRoot: 'C', scale: 'minor', partName: 'drums', styleId: 'lofi' },
      attachTo: document.body,
    })
    const el = wrapper.find('canvas').element as HTMLCanvasElement
    el.width = 800; el.height = 500
    el.getBoundingClientRect = () =>
      ({ left: 0, top: 0, right: 800, bottom: 500, width: 800, height: 500, x: 0, y: 0, toJSON() {} }) as DOMRect
    return wrapper
  }

  it('auditions a drum piece when its gutter row is clicked', async () => {
    const wrapper = mountDrums([drum(38, 0), drum(42, 0.5)])   // snare + hat lanes
    await clickFit(wrapper)
    await wrapper.find('canvas').trigger('mousedown', { clientX: 20, clientY: 200 })   // in the gutter
    window.dispatchEvent(new MouseEvent('mouseup', { clientX: 20, clientY: 200 }))
    expect(player.audition).toHaveBeenCalledTimes(1)
    const [styleId, part] = player.audition.mock.calls[0]
    expect(styleId).toBe('lofi'); expect(part).toBe('drums')
    wrapper.unmount()
  })

  it('exposes the Draw/Select tools and draws a hit as percussion', async () => {
    const wrapper = mountDrums([drum(38, 0)])
    await clickFit(wrapper)
    // The tool toggle is available on drum parts too.
    expect(wrapper.findAll('button').some(b => b.text().includes('Draw'))).toBe(true)
    expect(wrapper.findAll('button').some(b => b.text().includes('Select'))).toBe(true)
    // Draw is the default tool — clicking an empty lane adds a hit flagged percussion.
    await wrapper.find('canvas').trigger('mousedown', { clientX: 300, clientY: 200 })
    window.dispatchEvent(new MouseEvent('mouseup', { clientX: 300, clientY: 200 }))
    const [notes, dirty] = lastEmit(wrapper)!
    expect(dirty).toBe(true)
    expect(notes.length).toBe(2)                             // original + drawn hit
    expect(notes[notes.length - 1].isPercussion).toBe(true)  // drawn as a drum hit
    wrapper.unmount()
  })
})

// ── Song-mode sections (loop a section, record into it) ──────────────────────
describe('PianoRollEditor — sections', () => {
  // 4/4 editor: bar = 4 beats = 2.0s @ 120bpm (secondsPerBeat 0.5).
  const SECTIONS = [
    { name: 'Intro', section_type: 'intro', start_bar: 0, bars: 4 },
    { name: 'Verse 1', section_type: 'verse', start_bar: 4, bars: 8 },
    { name: 'Chorus', section_type: 'chorus', start_bar: 12, bars: 8 },
  ]
  const recBtn = (w: VueWrapper) => w.findAll('button').find(b => /rec/i.test(b.text()))!
  function mountWithSections() {
    const wrapper = mount(PianoRollEditor, {
      props: {
        notes: [melodic(60, 0.5)], duration: 40, secondsPerBeat: 0.5,
        keyRoot: 'C', scale: 'minor', partName: 'melody', styleId: 'lofi', sections: SECTIONS,
      },
      attachTo: document.body,
    })
    const el = wrapper.find('canvas').element as HTMLCanvasElement
    el.width = 800; el.height = 500
    el.getBoundingClientRect = () =>
      ({ left: 0, top: 0, right: 800, bottom: 500, width: 800, height: 500, x: 0, y: 0, toJSON() {} }) as DOMRect
    return wrapper
  }
  const sectionSelect = (w: VueWrapper) => w.findAll('select').find(s => s.text().includes('Verse 1'))

  it('shows a section selector in song mode but not in loop mode', async () => {
    const song = mountWithSections()
    await clickFit(song)
    expect(sectionSelect(song)).toBeTruthy()
    song.unmount()

    const loop = mountEditor([melodic(60, 0.5)])   // no sections
    await clickFit(loop)
    expect(loop.findAll('select').some(s => s.text().includes('Loop a section'))).toBe(false)
    loop.unmount()
  })

  it('selecting a section loops exactly its bar span in playback', async () => {
    const wrapper = mountWithSections()
    await clickFit(wrapper)
    // Verse 1: start_bar 4, 8 bars → beats 16..48 → 8.0s..24.0s.
    await sectionSelect(wrapper)!.setValue('1')
    await playBtn(wrapper).trigger('click')
    await flushPromises()
    const region = player.toggle.mock.calls[0][4]
    expect(region.start).toBeCloseTo(8.0)
    expect(region.end).toBeCloseTo(24.0)
    wrapper.unmount()
  })

  it('records an overdub into the selected section span', async () => {
    const wrapper = mountWithSections()
    await clickFit(wrapper)
    await sectionSelect(wrapper)!.setValue('2')   // Chorus: bars 12..20 → 24.0s..40.0s

    await recBtn(wrapper).trigger('click')        // arm — loops the chosen section
    await flushPromises()
    const region = player.toggle.mock.calls[0][4]
    expect(region.start).toBeCloseTo(24.0)
    expect(region.end).toBeCloseTo(40.0)

    recNoteCb!({ type: 'on', note: 64, velocity: 0.7 }); recNoteCb!({ type: 'off', note: 64, velocity: 0 })
    await recBtn(wrapper).trigger('click')        // stop → quantize + commit (unsaved)
    const [notes, dirty] = lastEmit(wrapper)!
    expect(notes.map(n => n.midi)).toContain(64)   // overdubbed note captured
    expect(dirty).toBe(true)
    expect(wrapper.emitted('save')).toBeFalsy()     // committed but left for the user to save
    wrapper.unmount()
  })
})

describe('PianoRollEditor — undo/redo', () => {
  const undoBtn = (w: VueWrapper) => w.findAll('button').find(b => b.text() === '↶')!
  const redoBtn = (w: VueWrapper) => w.findAll('button').find(b => b.text() === '↷')!

  it('undoes and redoes a note insertion', async () => {
    const wrapper = mountEditor([melodic(60, 0.5)])
    await clickFit(wrapper)
    expect(undoBtn(wrapper).attributes('disabled')).toBeDefined()   // nothing to undo yet

    // Insert a note (drag-to-create then release).
    await wrapper.find('canvas').trigger('mousedown', { clientX: 300, clientY: 220 })
    window.dispatchEvent(new MouseEvent('mouseup', { clientX: 300, clientY: 220 }))
    expect(lastEmit(wrapper)![0]).toHaveLength(2)

    // Undo via Ctrl+Z, then the toolbar redo button.
    await wrapper.find('canvas').trigger('keydown', { key: 'z', ctrlKey: true })
    expect(lastEmit(wrapper)![0]).toHaveLength(1)   // back to the original note
    expect(undoBtn(wrapper).attributes('disabled')).toBeDefined()   // nothing left to undo

    await redoBtn(wrapper).trigger('click')
    expect(lastEmit(wrapper)![0]).toHaveLength(2)   // insertion restored
    wrapper.unmount()
  })
})
