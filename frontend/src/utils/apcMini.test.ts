/*
 * GenreGrid — a style-based MIDI generator.
 * Copyright (C) 2026 Tw Dover
 *
 * This program is free software: you can redistribute it and/or modify it under
 * the terms of the GNU General Public License v3 or (at your option) any later
 * version. Distributed WITHOUT ANY WARRANTY. See <https://www.gnu.org/licenses/>.
 */
import { describe, it, expect } from 'vitest'
import {
  cellToPad, padToCell, padLedMsg, buttonLedMsg, blackoutMsgs, parseApcMessage,
  isApcMiniMk2, isApcMiniMk1, pickApcPort, rackCellToPitch, drumPadColor,
  noteGridPitch, noteGridBaseFor, diatonicTriad,
  APC_COLOR, APC_FX, APC_TRACK_BTN_BASE, APC_SCENE_BTN_BASE, APC_SHIFT_NOTE,
} from './apcMini'

describe('grid math', () => {
  it('maps cells to pad notes row-major from the bottom-left', () => {
    expect(cellToPad(0, 0)).toBe(0)     // bottom-left
    expect(cellToPad(7, 0)).toBe(7)     // bottom-right
    expect(cellToPad(0, 7)).toBe(56)    // top-left
    expect(cellToPad(7, 7)).toBe(63)    // top-right
  })
  it('padToCell inverts cellToPad across the whole grid', () => {
    for (let n = 0; n <= 63; n++) {
      const { col, row } = padToCell(n)
      expect(cellToPad(col, row)).toBe(n)
    }
  })
})

describe('LED messages', () => {
  it('encodes pad color as velocity and behavior as the channel nibble', () => {
    expect(padLedMsg(10, APC_COLOR.red, APC_FX.solid)).toEqual([0x96, 10, 5])
    expect(padLedMsg(63, APC_COLOR.green, APC_FX.blink)).toEqual([0x9e, 63, 21])
    expect(padLedMsg(0, APC_COLOR.off, APC_FX.solid10)).toEqual([0x90, 0, 0])
  })
  it('encodes single-color button LEDs on channel 0', () => {
    expect(buttonLedMsg(APC_TRACK_BTN_BASE, 1)).toEqual([0x90, 100, 1])
    expect(buttonLedMsg(APC_SCENE_BTN_BASE + 7, 2)).toEqual([0x90, 119, 2])
  })
  it('blackout covers all 64 pads and 16 buttons', () => {
    const msgs = blackoutMsgs()
    expect(msgs).toHaveLength(64 + 8 + 8)
    expect(msgs.every(m => m[2] === 0)).toBe(true)
  })
})

describe('parseApcMessage', () => {
  it('decodes pad presses with grid coordinates', () => {
    expect(parseApcMessage([0x90, 0, 127])).toEqual({ kind: 'pad', col: 0, row: 0, on: true, velocity: 127 })
    expect(parseApcMessage([0x80, 63, 0])).toEqual({ kind: 'pad', col: 7, row: 7, on: false, velocity: 0 })
    expect(parseApcMessage([0x90, 9, 0]).kind).toBe('pad')            // vel-0 note-on = release
    expect((parseApcMessage([0x90, 9, 0]) as { on: boolean }).on).toBe(false)
  })
  it('decodes track, scene, and shift buttons', () => {
    expect(parseApcMessage([0x90, 100, 127])).toEqual({ kind: 'track', index: 0, on: true })
    expect(parseApcMessage([0x80, 107, 0])).toEqual({ kind: 'track', index: 7, on: false })
    expect(parseApcMessage([0x90, 112, 127])).toEqual({ kind: 'scene', index: 0, on: true })
    expect(parseApcMessage([0x90, 119, 127])).toEqual({ kind: 'scene', index: 7, on: true })
    expect(parseApcMessage([0x90, APC_SHIFT_NOTE, 127])).toEqual({ kind: 'shift', on: true })
  })
  it('decodes faders as normalized values, master included', () => {
    expect(parseApcMessage([0xb0, 48, 127])).toEqual({ kind: 'fader', index: 0, value: 1 })
    expect(parseApcMessage([0xb0, 55, 0])).toEqual({ kind: 'fader', index: 7, value: 0 })
    expect(parseApcMessage([0xb0, 56, 64])).toEqual({ kind: 'fader', index: 8, value: 64 / 127 })
  })
  it('treats anything else as other', () => {
    expect(parseApcMessage([0xb0, 20, 5]).kind).toBe('other')   // unrelated CC
    expect(parseApcMessage([0x90, 90, 100]).kind).toBe('other') // note in the gap
    expect(parseApcMessage([0xf8]).kind).toBe('other')          // clock
  })
})

describe('device detection', () => {
  it('matches mk2 names in the shapes ALSA/CoreMIDI report', () => {
    expect(isApcMiniMk2('APC mini mk2')).toBe(true)
    expect(isApcMiniMk2('APC mini mk2 APC mini mk2 Control')).toBe(true)
    expect(isApcMiniMk2('Akai APC Mini MK2 MIDI 1')).toBe(true)
    expect(isApcMiniMk2('APC mini')).toBe(false)
    expect(isApcMiniMk2(null)).toBe(false)
  })
  it('flags an original APC mini as mk1', () => {
    expect(isApcMiniMk1('APC MINI MIDI 1')).toBe(true)
    expect(isApcMiniMk1('APC mini mk2 Control')).toBe(false)
    expect(isApcMiniMk1('Some Keyboard')).toBe(false)
  })
  it('prefers the Control port over the Notes port', () => {
    const ports = [
      { name: 'APC mini mk2 APC mini mk2 Notes' },
      { name: 'APC mini mk2 APC mini mk2 Control' },
    ]
    expect(pickApcPort(ports)?.name).toContain('Control')
    expect(pickApcPort([{ name: 'APC mini mk2' }])?.name).toBe('APC mini mk2')
    expect(pickApcPort([{ name: 'Test Keys' }])).toBeNull()
  })
})

describe('note grid', () => {
  it('stacks rows in fourths: chromatic across, +5 semitones per row up', () => {
    expect(noteGridPitch(0, 0, 48)).toBe(48)
    expect(noteGridPitch(7, 0, 48)).toBe(55)
    expect(noteGridPitch(0, 1, 48)).toBe(53)
    expect(noteGridPitch(7, 7, 48)).toBe(90)
  })
  it('returns null off the ends of the MIDI range', () => {
    expect(noteGridPitch(7, 7, 120)).toBeNull()   // 120 + 42 > 127
    expect(noteGridPitch(0, 0, -1)).toBeNull()
  })
  it('bases bass two octaves under the other voices', () => {
    expect(noteGridBaseFor('bass')).toBe(24)
    expect(noteGridBaseFor('melody')).toBe(48)
    expect(noteGridBaseFor('chords')).toBe(48)
  })
})

describe('chord grid', () => {
  const MAJOR = [0, 2, 4, 5, 7, 9, 11]
  it('builds diatonic triads: columns are degrees, rows are octaves', () => {
    expect(diatonicTriad(0, 0, 48, MAJOR)).toEqual([48, 52, 55])   // C  E  G
    expect(diatonicTriad(1, 0, 48, MAJOR)).toEqual([50, 53, 57])   // D  F  A (ii)
    expect(diatonicTriad(4, 0, 48, MAJOR)).toEqual([55, 59, 62])   // G  B  D (V)
    expect(diatonicTriad(6, 0, 48, MAJOR)).toEqual([59, 62, 65])   // B  D  F (vii°)
    expect(diatonicTriad(0, 1, 48, MAJOR)).toEqual([60, 64, 67])   // C one octave up
    expect(diatonicTriad(7, 0, 48, MAJOR)).toEqual([60, 64, 67])   // column 8 = I, octave up
  })
  it('respects the scale intervals (minor iv is minor)', () => {
    const MINOR = [0, 2, 3, 5, 7, 8, 10]
    expect(diatonicTriad(0, 0, 48, MINOR)).toEqual([48, 51, 55])   // C Eb G (i)
    expect(diatonicTriad(3, 0, 48, MINOR)).toEqual([53, 56, 60])   // F Ab C (iv)
  })
  it('returns null when the chord leaves MIDI range or the pad is off-grid', () => {
    expect(diatonicTriad(7, 7, 48, MAJOR)).toBeNull()   // 48 + 12*8 + … > 127
    expect(diatonicTriad(8, 0, 48, MAJOR)).toBeNull()
    expect(diatonicTriad(0, -1, 48, MAJOR)).toBeNull()
  })
})

describe('drum rack', () => {
  it('lays out GM 36..51 chromatically from the bottom-left pad', () => {
    expect(rackCellToPitch(0, 0)).toBe(36)   // kick
    expect(rackCellToPitch(2, 0)).toBe(38)   // snare
    expect(rackCellToPitch(2, 1)).toBe(42)   // closed hat
    expect(rackCellToPitch(3, 3)).toBe(51)   // ride
    expect(rackCellToPitch(4, 0)).toBeNull() // off the 4×4 rack
    expect(rackCellToPitch(0, 4)).toBeNull()
  })
  it('colors pads by kit-piece family', () => {
    expect(drumPadColor(36)).toBe(APC_COLOR.red)      // kick
    expect(drumPadColor(38)).toBe(APC_COLOR.orange)   // snare
    expect(drumPadColor(42)).toBe(APC_COLOR.yellow)   // hat
    expect(drumPadColor(45)).toBe(APC_COLOR.blue)     // tom
    expect(drumPadColor(49)).toBe(APC_COLOR.cyan)     // crash
    expect(drumPadColor(60)).toBe(APC_COLOR.purple)   // misc percussion
  })
})
