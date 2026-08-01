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

// Mock the audio engine — the driver drives it, we assert the calls.
const player = {
  auditionOn: vi.fn(), auditionOff: vi.fn(), prepareAudition: vi.fn(),
  toggleMute: vi.fn(), soloPart: vi.fn(), setPartLevel: vi.fn(), setVolume: vi.fn(),
  playPause: vi.fn(), stop: vi.fn(), setLooping: vi.fn(),
  channelMuted: ref({ drums: false, bass: false, chords: false, melody: false, arpeggio: false, pads: false, counter_melody: false }),
  looping: ref(false), currentlyPlaying: ref<string | null>(null), isPaused: ref(false),
}
vi.mock('./useMidiPlayer', () => ({ useMidiPlayer: () => player }))

// Mock the metronome (the real one schedules Tone events).
const metro = {
  enabled: ref(false),
  setEnabled: vi.fn((v: boolean) => { metro.enabled.value = v }),
  startTicking: vi.fn(), stopTicking: vi.fn(),
  startStandalone: vi.fn(), stopStandalone: vi.fn(),
}
vi.mock('./useMetronome', () => ({ useMetronome: () => metro }))

import { useMidiInput, setAuditionTarget, clearAuditionTarget } from './useMidiInput'
import { registerApcMiniDriver, registerStepSurface, useApcMini, type StepSurface } from './useApcMini'

type FakeInput = { id: string; name: string; onmidimessage: ((e: { data: Uint8Array }) => void) | null }
type FakeOutput = { id: string; name: string; send: ReturnType<typeof vi.fn> }

function makeAccess() {
  const keys: FakeInput = { id: 'keys', name: 'Test Keys', onmidimessage: null }
  const apcIn: FakeInput = { id: 'apc-in', name: 'APC mini mk2 APC mini mk2 Control', onmidimessage: null }
  const apcOut: FakeOutput = { id: 'apc-out', name: 'APC mini mk2 APC mini mk2 Control', send: vi.fn() }
  return {
    keys, apcIn, apcOut,
    access: {
      inputs: new Map([['keys', keys], ['apc-in', apcIn]]),
      outputs: new Map([['apc-out', apcOut]]),
      onstatechange: null as ((e: unknown) => void) | null,
    },
  }
}

function press(input: FakeInput, data: number[]) {
  input.onmidimessage!({ data: new Uint8Array(data) })
}

describe('APC mini mk2 driver', () => {
  let f: ReturnType<typeof makeAccess>

  beforeEach(async () => {
    vi.clearAllMocks()
    player.currentlyPlaying.value = null
    player.looping.value = false
    f = makeAccess()
    ;(navigator as unknown as { requestMIDIAccess: unknown }).requestMIDIAccess =
      vi.fn().mockResolvedValue(f.access)
    registerApcMiniDriver()
    const midi = useMidiInput()
    midi.disable()
    midi.setPart('melody')                 // reset the module singleton between cases
    clearAuditionTarget()
    metro.enabled.value = false
    const apc = useApcMini()
    apc.octaveShift.value = 0
    apc.padVelocity.value = 0.8
    await midi.enable()
  })

  it('claims the APC ports: connected, LEDs initialized, port off the device list', () => {
    const apc = useApcMini()
    expect(apc.connected.value).toBe(true)
    expect(f.apcIn.onmidimessage).toBeTypeOf('function')
    // Blackout (80 LEDs) plus the initial frame render.
    expect(f.apcOut.send.mock.calls.length).toBeGreaterThanOrEqual(80)
    // The claimed control port is not offered as a generic input.
    const midi = useMidiInput()
    expect(midi.devices.value.map(d => d.id)).toEqual(['keys'])
  })

  it('plays rack pads as drums when drums is the target voice', () => {
    useMidiInput().setPart('drums')
    press(f.apcIn, [0x90, 0, 127])   // bottom-left pad = GM 36 kick
    expect(player.auditionOn).toHaveBeenCalledWith(undefined, 'drums', 36, 0.8)
    // Held pad renders white at full brightness (channel 6 → status 0x96, white=3).
    expect(f.apcOut.send.mock.calls.some(c => c[0][0] === 0x96 && c[0][1] === 0 && c[0][2] === 3)).toBe(true)
    press(f.apcIn, [0x80, 0, 0])
    expect(player.auditionOff).toHaveBeenCalledWith(undefined, 'drums', 36)
  })

  it('ignores pads outside the 4×4 rack when targeting drums', () => {
    useMidiInput().setPart('drums')
    press(f.apcIn, [0x90, 63, 127])   // top-right pad
    expect(player.auditionOn).not.toHaveBeenCalled()
  })

  it('plays the full grid as a note grid in fourths for melodic voices', () => {
    press(f.apcIn, [0x90, 0, 127])    // bottom-left = C3 (48) for melody
    expect(player.auditionOn).toHaveBeenCalledWith(undefined, 'melody', 48, 0.8)
    press(f.apcIn, [0x90, 63, 127])   // top-right = 48 + 7*5 + 7 = 90
    expect(player.auditionOn).toHaveBeenCalledWith(undefined, 'melody', 90, 0.8)
    press(f.apcIn, [0x80, 0, 0])
    expect(player.auditionOff).toHaveBeenCalledWith(undefined, 'melody', 48)
  })

  it('follows the selected voice, and bass sits two octaves down', () => {
    useMidiInput().setPart('bass')
    press(f.apcIn, [0x90, 0, 127])    // bottom-left = C1 (24) for bass
    expect(player.auditionOn).toHaveBeenCalledWith(undefined, 'bass', 24, 0.8)
  })

  it('shifts the note grid by octaves from scene buttons and releases held notes', () => {
    press(f.apcIn, [0x90, 0, 127])     // hold C3
    press(f.apcIn, [0x90, 116, 127])   // scene 5 = octave up
    expect(player.auditionOff).toHaveBeenCalledWith(undefined, 'melody', 48)   // no stuck note
    press(f.apcIn, [0x90, 0, 127])
    expect(player.auditionOn).toHaveBeenCalledWith(undefined, 'melody', 60, 0.8)
    press(f.apcIn, [0x90, 117, 127])   // scene 6 = octave down (back to C3)
    press(f.apcIn, [0x90, 8, 127])     // row 1, col 0 = 48 + 5
    expect(player.auditionOn).toHaveBeenCalledWith(undefined, 'melody', 53, 0.8)
  })

  it('maps faders to part levels and the master fader to volume', () => {
    press(f.apcIn, [0xb0, 48, 127])
    expect(player.setPartLevel).toHaveBeenCalledWith('drums', 1)
    press(f.apcIn, [0xb0, 49, 0])
    expect(player.setPartLevel).toHaveBeenCalledWith('bass', 0)
    press(f.apcIn, [0xb0, 56, 127])
    expect(player.setVolume).toHaveBeenCalledWith(100)
  })

  it('drives transport from the scene buttons and mutes from the track buttons', () => {
    press(f.apcIn, [0x90, 112, 127])   // scene 1 = play/pause
    expect(player.playPause).toHaveBeenCalled()
    press(f.apcIn, [0x90, 113, 127])   // scene 2 = stop
    expect(player.stop).toHaveBeenCalled()
    press(f.apcIn, [0x90, 114, 127])   // scene 3 = loop toggle
    expect(player.setLooping).toHaveBeenCalledWith(true)
    press(f.apcIn, [0x90, 100, 127])   // track 1 = mute drums
    expect(player.toggleMute).toHaveBeenCalledWith('drums')
    press(f.apcIn, [0x90, 103, 127])   // track 4 = mute melody
    expect(player.toggleMute).toHaveBeenCalledWith('melody')
  })

  it('plays diatonic triads on the chords voice (C major by default)', () => {
    useMidiInput().setPart('chords')
    press(f.apcIn, [0x90, 0, 127])    // bottom-left = I chord
    expect(player.auditionOn.mock.calls.map(c => c[2])).toEqual([48, 52, 55])   // C E G
    expect(player.auditionOn.mock.calls.every(c => c[1] === 'chords')).toBe(true)
    press(f.apcIn, [0x80, 0, 0])
    expect(player.auditionOff.mock.calls.map(c => c[2])).toEqual([48, 52, 55])
  })

  it('builds chords in the audition target key when an editor provides one', () => {
    useMidiInput().setPart('chords')
    setAuditionTarget('lofi', 'chords', 'A', 'minor')
    press(f.apcIn, [0x90, 0, 127])    // i chord of A minor, base C3+9 = A3
    expect(player.auditionOn.mock.calls.map(c => c[2])).toEqual([57, 60, 64])   // A C E
  })

  it('sets pad velocity from fader 8', () => {
    press(f.apcIn, [0xb0, 55, 64])    // fader 8 ≈ half
    press(f.apcIn, [0x90, 0, 127])
    expect(player.auditionOn).toHaveBeenCalledWith(undefined, 'melody', 48, 64 / 127)
  })

  it('solos parts from the track buttons while Shift is held', () => {
    press(f.apcIn, [0x90, 122, 127])   // shift down
    press(f.apcIn, [0x90, 103, 127])   // track 4
    expect(player.soloPart).toHaveBeenCalledWith('melody')
    expect(player.toggleMute).not.toHaveBeenCalled()
    press(f.apcIn, [0x80, 122, 0])     // shift up
    press(f.apcIn, [0x90, 103, 127])
    expect(player.toggleMute).toHaveBeenCalledWith('melody')
  })

  it('toggles the metronome from scene 7 (standalone when nothing plays)', () => {
    press(f.apcIn, [0x90, 118, 127])
    expect(metro.setEnabled).toHaveBeenCalledWith(true)
    expect(metro.startStandalone).toHaveBeenCalled()
    press(f.apcIn, [0x90, 118, 127])
    expect(metro.setEnabled).toHaveBeenCalledWith(false)
    expect(metro.stopStandalone).toHaveBeenCalled()
  })

  it('keeps routing other inputs through the generic note path', () => {
    press(f.keys, [0x90, 60, 100])
    expect(player.auditionOn).toHaveBeenCalledWith(undefined, 'melody', 60, 100 / 127)
  })

  it('switches to the step sequencer while a surface is registered and edits steps', () => {
    const steps = new Set<string>()
    const surface: StepSurface = {
      lanes: () => [{ pitch: 36, name: 'Kick' }, { pitch: 38, name: 'Snare' }],
      stepCount: () => 16,
      stepAt: (l, s) => steps.has(`${l}:${s}`),
      toggleStep: vi.fn((l, s) => {
        const k = `${l}:${s}`
        if (steps.has(k)) steps.delete(k); else steps.add(k)
      }),
      playheadStep: () => -1,
      recording: () => false,
      toggleRecord: vi.fn(),
    }
    const unregister = registerStepSurface(surface)
    const apc = useApcMini()

    press(f.apcIn, [0x90, 119, 127])   // scene 8 = grid-mode toggle
    expect(apc.gridMode.value).toBe('steps')

    press(f.apcIn, [0x90, 2, 127])     // bottom row, col 2 → lane 0 step 2
    expect(surface.toggleStep).toHaveBeenCalledWith(0, 2)
    expect(player.auditionOn).not.toHaveBeenCalled()   // step edits don't trigger pads

    press(f.apcIn, [0x90, 101, 127])   // track 2 = page 2 (steps 8..15 exist)
    press(f.apcIn, [0x90, 8, 127])     // row 1, col 0 → lane 1 step 8
    expect(surface.toggleStep).toHaveBeenCalledWith(1, 8)

    press(f.apcIn, [0x90, 115, 127])   // scene 4 = record
    expect(surface.toggleRecord).toHaveBeenCalled()

    // Closing the editor drops back to pads mode.
    unregister()
    expect(apc.gridMode.value).toBe('pads')
  })

  it('turns the lights off and disconnects on disable', () => {
    const apc = useApcMini()
    f.apcOut.send.mockClear()
    useMidiInput().disable()
    expect(apc.connected.value).toBe(false)
    expect(f.apcOut.send.mock.calls.length).toBeGreaterThanOrEqual(80)   // blackout
    expect(f.apcOut.send.mock.calls.every(c => c[0][2] === 0)).toBe(true)
  })
})
