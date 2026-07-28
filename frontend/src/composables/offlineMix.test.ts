/*
 * GenreGrid — a style-based MIDI generator.
 * Copyright (C) 2026 Tw Dover
 *
 * This program is free software: you can redistribute it and/or modify it under
 * the terms of the GNU General Public License as published by the Free Software
 * Foundation, either version 3 of the License, or (at your option) any later
 * version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
 * <https://www.gnu.org/licenses/> for details.
 */
import { describe, it, expect } from 'vitest'
import { sumPartBuffers } from './useMidiPlayer'

// Minimal stand-in for the parts of AudioBuffer sumPartBuffers reads. (jsdom has no
// Web Audio, and the summing logic is pure, so a fake is enough to test the maths.)
function fakeBuffer(channels: number[][], sampleRate = 44100) {
  return {
    length: channels[0].length,
    sampleRate,
    numberOfChannels: channels.length,
    getChannelData: (c: number) => Float32Array.from(channels[c]),
  }
}

describe('sumPartBuffers', () => {
  it('sums stereo parts sample-by-sample per channel', () => {
    const a = fakeBuffer([[0.1, 0.2, 0.3], [-0.1, -0.2, -0.3]])
    const b = fakeBuffer([[0.4, 0.4, 0.4], [0.05, 0.05, 0.05]])
    const { length, sampleRate, channels } = sumPartBuffers([a, b])
    expect(length).toBe(3)
    expect(sampleRate).toBe(44100)
    expect(Array.from(channels[0])).toEqual([
      expect.closeTo(0.5), expect.closeTo(0.6), expect.closeTo(0.7),
    ])
    expect(Array.from(channels[1])).toEqual([
      expect.closeTo(-0.05), expect.closeTo(-0.15), expect.closeTo(-0.25),
    ])
  })

  it('is the identity for a single part (parallel path === single-pass pre-limiter mix)', () => {
    const only = fakeBuffer([[0.2, -0.4, 0.6], [0.1, -0.2, 0.3]])
    const { channels } = sumPartBuffers([only])
    expect(Array.from(channels[0])).toEqual([
      expect.closeTo(0.2), expect.closeTo(-0.4), expect.closeTo(0.6),
    ])
    expect(Array.from(channels[1])).toEqual([
      expect.closeTo(0.1), expect.closeTo(-0.2), expect.closeTo(0.3),
    ])
  })

  it('upmixes a mono part to both output channels', () => {
    const mono = fakeBuffer([[1, 1, 1]])   // one channel only
    const { channels } = sumPartBuffers([mono])
    expect(Array.from(channels[0])).toEqual([1, 1, 1])
    expect(Array.from(channels[1])).toEqual([1, 1, 1])   // mono fed to R too
  })

  it('handles parts of differing lengths (mix spans the longest)', () => {
    const long = fakeBuffer([[0.1, 0.1, 0.1, 0.1], [0, 0, 0, 0]])
    const short = fakeBuffer([[0.5, 0.5], [0.5, 0.5]])
    const { length, channels } = sumPartBuffers([long, short])
    expect(length).toBe(4)
    expect(Array.from(channels[0])).toEqual([
      expect.closeTo(0.6), expect.closeTo(0.6), expect.closeTo(0.1), expect.closeTo(0.1),
    ])
  })
})
