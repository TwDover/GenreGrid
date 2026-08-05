/*
 * GenreGrid — a style-based MIDI generator.
 * Copyright (C) 2026 Tw Dover
 *
 * This program is free software: you can redistribute it and/or modify it under
 * the terms of the GNU General Public License v3 or (at your option) any later
 * version. Distributed WITHOUT ANY WARRANTY. See <https://www.gnu.org/licenses/>.
 */
// jsdom has no real Web Audio / getUserMedia, so Tone is faked the same way
// useAudioRecorder.test.ts fakes it — this exercises usePitchDetect's own
// orchestration (start/stop/detect/error states), not real mic capture or
// audio decoding. The detection algorithm itself is validated with
// synthesized signals in pitchDetect.test.ts; here it's fed a fake decoded
// buffer to prove the composable wires capture -> decode -> detect -> quantize
// correctly.
import { vi, describe, it, expect, beforeEach } from 'vitest'

const SR = 44100
function sineWave(freq: number, durationSec: number, sampleRate = SR, amplitude = 0.5): Float32Array {
  const n = Math.round(durationSec * sampleRate)
  const out = new Float32Array(n)
  for (let i = 0; i < n; i++) out[i] = amplitude * Math.sin((2 * Math.PI * freq * i) / sampleRate)
  return out
}

const { state, FakeUserMedia, FakeRecorder, FakeGain, FakeMeter } = vi.hoisted(() => {
  const state = {
    openShouldFail: false,
    stopBlob: new Blob(['take']),
    decoded: { sampleRate: 44100, samples: new Float32Array(1) },
  }

  class FakeUserMedia {
    static instances: FakeUserMedia[] = []
    static async enumerateDevices() { return [] }
    connected: unknown[] = []
    closed = false
    disposed = false
    constructor() { FakeUserMedia.instances.push(this) }
    async open() { if (state.openShouldFail) throw new Error('permission denied') }
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
    constructor(v: number) { this.gain.value = v }
    toDestination() { return this }
    dispose() {}
  }

  class FakeMeter {
    getValue() { return 0 }
    dispose() {}
  }

  return { state, FakeUserMedia, FakeRecorder, FakeGain, FakeMeter }
})

vi.mock('tone', () => ({
  start: vi.fn(async () => {}),
  UserMedia: FakeUserMedia,
  Recorder: FakeRecorder,
  Gain: FakeGain,
  Meter: FakeMeter,
  getContext: () => ({
    rawContext: {
      decodeAudioData: async () => ({
        sampleRate: state.decoded.sampleRate,
        getChannelData: () => state.decoded.samples,
      }),
    },
  }),
}))

import { usePitchDetect } from './usePitchDetect'

beforeEach(() => {
  state.openShouldFail = false
  state.decoded = { sampleRate: SR, samples: new Float32Array(1) }
  FakeUserMedia.instances = []
  FakeRecorder.instances = []
})

describe('usePitchDetect', () => {
  it('detects and quantizes a hummed take into notes', async () => {
    const c4 = sineWave(261.63, 0.3)
    const e4 = sineWave(329.63, 0.3)
    const g4 = sineWave(392.0, 0.3)
    const c5 = sineWave(523.25, 0.3)
    const gap = new Float32Array(Math.round(0.08 * SR))
    const parts = [c4, gap, e4, gap, g4, gap, c5]
    const total = parts.reduce((s, p) => s + p.length, 0)
    const buffer = new Float32Array(total)
    let offset = 0
    for (const p of parts) { buffer.set(p, offset); offset += p.length }
    state.decoded = { sampleRate: SR, samples: buffer }

    const pd = usePitchDetect()
    await pd.start()
    expect(pd.isRecording.value).toBe(true)
    const notes = await pd.stopAndDetect(120)
    expect(pd.isRecording.value).toBe(false)
    expect(pd.processing.value).toBe(false)
    expect(pd.detectError.value).toBeNull()
    expect(notes.map(n => n.pitch)).toEqual([60, 64, 67, 72])
    expect(pd.notes.value).toEqual(notes)
    // All beats/durations should be non-negative and grid-aligned to 0.25 beat.
    for (const n of notes) {
      expect(n.start).toBeGreaterThanOrEqual(0)
      expect(Number.isInteger(n.start / 0.25)).toBe(true)
    }
  })

  it('sets detectError and empties notes when the take has no clear melody', async () => {
    state.decoded = { sampleRate: SR, samples: new Float32Array(SR) } // silence
    const pd = usePitchDetect()
    await pd.start()
    const notes = await pd.stopAndDetect(120)
    expect(notes).toEqual([])
    expect(pd.notes.value).toEqual([])
    expect(pd.detectError.value).toMatch(/melody/i)
  })

  it('cancel() clears any previously detected notes and error', async () => {
    state.decoded = { sampleRate: SR, samples: new Float32Array(SR) }
    const pd = usePitchDetect()
    await pd.start()
    await pd.stopAndDetect(120)
    expect(pd.detectError.value).not.toBeNull()
    await pd.start()
    pd.cancel()
    expect(pd.notes.value).toEqual([])
    expect(pd.detectError.value).toBeNull()
    expect(pd.isRecording.value).toBe(false)
  })

  it('surfaces a mic permission failure via recordError', async () => {
    state.openShouldFail = true
    const pd = usePitchDetect()
    await expect(pd.start()).rejects.toThrow()
    expect(pd.recordError.value).toMatch(/microphone/i)
  })
})
