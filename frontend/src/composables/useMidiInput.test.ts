/*
 * GenreGrid — a style-based MIDI generator.
 * Copyright (C) 2026 Tw Dover
 *
 * This program is free software: you can redistribute it and/or modify it under
 * the terms of the GNU General Public License v3 or (at your option) any later
 * version. Distributed WITHOUT ANY WARRANTY. See <https://www.gnu.org/licenses/>.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock the audio engine so routing is assertable without Tone.
const player = { auditionOn: vi.fn(), auditionOff: vi.fn(), prepareAudition: vi.fn() }
vi.mock('./useMidiPlayer', () => ({ useMidiPlayer: () => player }))

import { useMidiInput, parseMidiMessage } from './useMidiInput'
import { activeStyleId } from './useStyleCatalog'

describe('parseMidiMessage', () => {
  it('decodes note-on, note-off, and note-on-with-zero-velocity as note-off', () => {
    expect(parseMidiMessage([0x90, 60, 100])).toEqual({ type: 'noteon', note: 60, velocity: 100 })
    expect(parseMidiMessage([0x80, 60, 64])).toEqual({ type: 'noteoff', note: 60, velocity: 0 })
    expect(parseMidiMessage([0x90, 60, 0])).toEqual({ type: 'noteoff', note: 60, velocity: 0 })
  })

  it('ignores the channel nibble and treats non-note messages as other', () => {
    expect(parseMidiMessage([0x95, 62, 80]).type).toBe('noteon')   // note-on, channel 6
    expect(parseMidiMessage([0x8a, 62, 0]).type).toBe('noteoff')   // note-off, channel 11
    expect(parseMidiMessage([0xb0, 74, 20]).type).toBe('other')    // CC
    expect(parseMidiMessage([0xf8]).type).toBe('other')            // clock
  })
})

describe('useMidiInput — routing', () => {
  let access: { inputs: Map<string, { id: string; name: string; onmidimessage: ((e: { data: Uint8Array }) => void) | null }>; onstatechange: ((e: unknown) => void) | null }

  beforeEach(() => {
    player.auditionOn.mockClear(); player.auditionOff.mockClear(); player.prepareAudition.mockClear()
    activeStyleId.value = null
    const input = { id: 'dev1', name: 'Test Keys', onmidimessage: null as ((e: { data: Uint8Array }) => void) | null }
    access = { inputs: new Map([['dev1', input]]), onstatechange: null }
    ;(navigator as unknown as { requestMIDIAccess: unknown }).requestMIDIAccess = vi.fn().mockResolvedValue(access)
    // Reset the module singleton between cases.
    const midi = useMidiInput()
    midi.disable()
    midi.selectedId.value = null
    midi.setPart('melody')
  })

  it('enables, lists the device, and warms the voice', async () => {
    const midi = useMidiInput()
    await midi.enable()
    expect(midi.enabled.value).toBe(true)
    expect(midi.devices.value).toEqual([{ id: 'dev1', name: 'Test Keys' }])
    expect(player.prepareAudition).toHaveBeenCalledWith(undefined, 'melody', true)
  })

  it('routes note-on/off to auditionOn/auditionOff with scaled velocity', async () => {
    const midi = useMidiInput()
    await midi.enable()
    const input = access.inputs.get('dev1')!
    input.onmidimessage!({ data: new Uint8Array([0x90, 60, 100]) })
    expect(player.auditionOn).toHaveBeenCalledWith(undefined, 'melody', 60, 100 / 127)
    input.onmidimessage!({ data: new Uint8Array([0x80, 60, 0]) })
    expect(player.auditionOff).toHaveBeenCalledWith(undefined, 'melody', 60)
  })

  it('plays the active style and the selected part', async () => {
    activeStyleId.value = 'lofi'
    const midi = useMidiInput()
    midi.setPart('bass')
    await midi.enable()
    access.inputs.get('dev1')!.onmidimessage!({ data: new Uint8Array([0x90, 40, 90]) })
    expect(player.auditionOn).toHaveBeenCalledWith('lofi', 'bass', 40, 90 / 127)
  })

  it('honors the device filter (ignores messages from other inputs)', async () => {
    const midi = useMidiInput()
    await midi.enable()
    midi.selectedId.value = 'some-other-device'
    access.inputs.get('dev1')!.onmidimessage!({ data: new Uint8Array([0x90, 60, 100]) })
    expect(player.auditionOn).not.toHaveBeenCalled()
  })

  it('disable() unbinds handlers and clears the enabled flag', async () => {
    const midi = useMidiInput()
    await midi.enable()
    const input = access.inputs.get('dev1')!
    expect(input.onmidimessage).toBeTypeOf('function')
    midi.disable()
    expect(input.onmidimessage).toBeNull()
    expect(midi.enabled.value).toBe(false)
  })
})
