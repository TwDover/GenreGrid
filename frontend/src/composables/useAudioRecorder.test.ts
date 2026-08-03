/*
 * GenreGrid — a style-based MIDI generator.
 * Copyright (C) 2026 Tw Dover
 *
 * This program is free software: you can redistribute it and/or modify it under
 * the terms of the GNU General Public License v3 or (at your option) any later
 * version. Distributed WITHOUT ANY WARRANTY. See <https://www.gnu.org/licenses/>.
 */
// jsdom has no real Web Audio / getUserMedia, so Tone's UserMedia/Recorder/Gain
// are faked here — this exercises the composable's own state machine (arm,
// permission failure, monitoring toggle, stop/cancel cleanup), not real audio
// capture (that's verified via a real-shell scenario, mirroring how
// synthDrums.test.ts fakes Tone for the same reason).
import { vi, describe, it, expect, beforeEach } from 'vitest'

// vi.mock factories are hoisted above the whole file, so the fakes + shared
// state have to be built inside vi.hoisted() (mirrors synthDrums.test.ts).
const { state, FakeUserMedia, FakeRecorder, FakeGain, FakeMeter } = vi.hoisted(() => {
  const state = {
    openShouldFail: false, stopBlob: new Blob(['take']),
    devices: [
      { deviceId: 'default', label: 'Default Mic' },
      { deviceId: 'usb-1', label: 'USB Headset' },
    ] as MediaDeviceInfo[],
    level: 0,
  }

  class FakeUserMedia {
    static instances: FakeUserMedia[] = []
    static async enumerateDevices() { return state.devices }
    connected: unknown[] = []
    closed = false
    disposed = false
    openedWith: string | number | undefined = undefined
    constructor() { FakeUserMedia.instances.push(this) }
    async open(deviceId?: string | number) {
      if (state.openShouldFail) throw new Error('permission denied')
      this.openedWith = deviceId
    }
    connect(dest: unknown) { this.connected.push(dest); return this }
    close() { this.closed = true; return this }
    dispose() { this.disposed = true; return this }
  }

  class FakeRecorder {
    static instances: FakeRecorder[] = []
    started = false
    disposed = false
    constructor() { FakeRecorder.instances.push(this) }
    start() { this.started = true }
    async stop() { this.started = false; return state.stopBlob }
    dispose() { this.disposed = true }
  }

  class FakeGain {
    gain = { value: 0 }
    disposed = false
    constructor(v: number) { this.gain.value = v }
    toDestination() { return this }
    dispose() { this.disposed = true }
  }

  class FakeMeter {
    static instances: FakeMeter[] = []
    disposed = false
    constructor() { FakeMeter.instances.push(this) }
    getValue() { return state.level }
    dispose() { this.disposed = true }
  }

  return { state, FakeUserMedia, FakeRecorder, FakeGain, FakeMeter }
})

vi.mock('tone', () => ({
  start: vi.fn(async () => {}),
  UserMedia: FakeUserMedia,
  Recorder: FakeRecorder,
  Gain: FakeGain,
  Meter: FakeMeter,
  getContext: () => ({ rawContext: {} }),
}))

import { useAudioRecorder } from './useAudioRecorder'

beforeEach(() => {
  state.openShouldFail = false
  state.level = 0
  FakeUserMedia.instances = []
  FakeRecorder.instances = []
  FakeMeter.instances = []
})

describe('useAudioRecorder', () => {
  it('starts recording: opens the mic, connects it to the recorder, a monitor gain, and a level meter', async () => {
    const rec = useAudioRecorder()
    await rec.start()
    expect(rec.isRecording.value).toBe(true)
    expect(rec.error.value).toBeNull()
    const mic = FakeUserMedia.instances[FakeUserMedia.instances.length - 1]
    expect(mic.connected.length).toBe(3)   // recorder + monitor gain + level meter
    expect(FakeRecorder.instances[FakeRecorder.instances.length - 1].started).toBe(true)
    await rec.stop()
  })

  it('opens a specific input device when given a deviceId', async () => {
    const rec = useAudioRecorder()
    await rec.start('usb-1')
    const mic = FakeUserMedia.instances[FakeUserMedia.instances.length - 1]
    expect(mic.openedWith).toBe('usb-1')
    await rec.stop()
  })

  it('lists audio input devices', async () => {
    const rec = useAudioRecorder()
    const devices = await rec.listInputDevices()
    expect(devices.map(d => d.deviceId)).toEqual(['default', 'usb-1'])
  })

  it('getLevel reflects the live meter while recording, 0 otherwise', async () => {
    const rec = useAudioRecorder()
    expect(rec.getLevel()).toBe(0)   // no meter before start()
    state.level = 0.42
    await rec.start()
    expect(rec.getLevel()).toBeCloseTo(0.42)
    await rec.stop()
    expect(rec.getLevel()).toBe(0)   // meter disposed on stop
  })

  it('sets error and rejects when mic permission is denied', async () => {
    state.openShouldFail = true
    const rec = useAudioRecorder()
    await expect(rec.start()).rejects.toThrow()
    expect(rec.isRecording.value).toBe(false)
    expect(rec.error.value).toMatch(/microphone/i)
  })

  it('stop() returns the captured blob and clears isRecording', async () => {
    const rec = useAudioRecorder()
    await rec.start()
    const blob = await rec.stop()
    expect(blob).toBe(state.stopBlob)
    expect(rec.isRecording.value).toBe(false)
  })

  it('cancel() tears down without needing a caller to await a blob', async () => {
    const rec = useAudioRecorder()
    await rec.start()
    const recorderInstance = FakeRecorder.instances[FakeRecorder.instances.length - 1]
    rec.cancel()
    expect(rec.isRecording.value).toBe(false)
    expect(recorderInstance.disposed).toBe(true)
  })

  it('setMonitoring toggles the live monitor gain', async () => {
    const rec = useAudioRecorder()
    expect(rec.monitoring.value).toBe(false)
    rec.setMonitoring(true)
    expect(rec.monitoring.value).toBe(true)
    await rec.start()   // gain node is created at start(), reflecting the current setting
    await rec.stop()
  })

  it('a second start() while already recording is a no-op', async () => {
    const rec = useAudioRecorder()
    await rec.start()
    const before = FakeUserMedia.instances.length
    await rec.start()
    expect(FakeUserMedia.instances.length).toBe(before)   // no second mic opened
    await rec.stop()
  })
})
