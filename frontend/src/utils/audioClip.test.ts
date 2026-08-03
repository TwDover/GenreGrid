/*
 * GenreGrid — a style-based MIDI generator.
 * Copyright (C) 2026 Tw Dover
 *
 * This program is free software: you can redistribute it and/or modify it under
 * the terms of the GNU General Public License v3 or (at your option) any later
 * version. Distributed WITHOUT ANY WARRANTY. See <https://www.gnu.org/licenses/>.
 */
import { describe, it, expect } from 'vitest'
import { fitBufferToDuration, placeClipInMix, waveformPeaks, type AudioBufferLike } from './audioClip'

function fakeBuffer(samplesPerChannel: number[][], sampleRate = 1000): AudioBufferLike {
  return {
    length: samplesPerChannel[0]?.length ?? 0,
    sampleRate,
    numberOfChannels: samplesPerChannel.length,
    getChannelData: (c: number) => Float32Array.from(samplesPerChannel[c]),
  }
}

describe('fitBufferToDuration', () => {
  it('pads a short buffer with trailing silence', () => {
    const buf = fakeBuffer([[1, 1, 1]])   // 3 samples @ 1000Hz = 3ms
    const fitted = fitBufferToDuration(buf, 0.005)   // target 5ms = 5 samples
    expect(fitted.length).toBe(5)
    expect(Array.from(fitted.channels[0])).toEqual([1, 1, 1, 0, 0])
  })

  it('trims a long buffer to the target length', () => {
    const buf = fakeBuffer([[1, 2, 3, 4, 5]])   // 5ms
    const fitted = fitBufferToDuration(buf, 0.003)   // target 3ms = 3 samples
    expect(fitted.length).toBe(3)
    expect(Array.from(fitted.channels[0])).toEqual([1, 2, 3])
  })

  it('fits every channel independently, preserving channel count', () => {
    const buf = fakeBuffer([[1, 1], [2, 2]])
    const fitted = fitBufferToDuration(buf, 0.003)
    expect(fitted.numberOfChannels).toBe(2)
    expect(Array.from(fitted.channels[0])).toEqual([1, 1, 0])
    expect(Array.from(fitted.channels[1])).toEqual([2, 2, 0])
  })

  it('never produces a zero-length buffer', () => {
    const buf = fakeBuffer([[1]])
    const fitted = fitBufferToDuration(buf, 0)
    expect(fitted.length).toBeGreaterThanOrEqual(1)
  })

  it('an exact-length buffer round-trips unchanged', () => {
    const buf = fakeBuffer([[1, 2, 3, 4]])
    const fitted = fitBufferToDuration(buf, 0.004)
    expect(fitted.length).toBe(4)
    expect(Array.from(fitted.channels[0])).toEqual([1, 2, 3, 4])
  })
})

describe('placeClipInMix', () => {
  it('places the clip at the given offset within a longer silent buffer', () => {
    const clip = fakeBuffer([[1, 1, 1]])   // 3 samples @ 1000Hz
    const placed = placeClipInMix(clip, 0.005, 10)   // offset 5 samples, total 10
    expect(placed.length).toBe(10)
    expect(Array.from(placed.getChannelData(0))).toEqual([0, 0, 0, 0, 0, 1, 1, 1, 0, 0])
  })

  it('places at offset 0 when offsetSeconds is 0', () => {
    const clip = fakeBuffer([[2, 2]])
    const placed = placeClipInMix(clip, 0, 5)
    expect(Array.from(placed.getChannelData(0))).toEqual([2, 2, 0, 0, 0])
  })

  it('truncates a clip that would run past the total length', () => {
    const clip = fakeBuffer([[1, 1, 1, 1, 1]])
    const placed = placeClipInMix(clip, 0.003, 5)   // offset 3, only 2 samples fit
    expect(Array.from(placed.getChannelData(0))).toEqual([0, 0, 0, 1, 1])
  })

  it('drops a clip whose offset is already past the total length', () => {
    const clip = fakeBuffer([[1, 1]])
    const placed = placeClipInMix(clip, 0.02, 5)   // offset 20, total 5
    expect(Array.from(placed.getChannelData(0))).toEqual([0, 0, 0, 0, 0])
  })

  it('preserves channel count', () => {
    const clip = fakeBuffer([[1, 1], [2, 2]])
    const placed = placeClipInMix(clip, 0, 4)
    expect(placed.numberOfChannels).toBe(2)
    expect(Array.from(placed.getChannelData(1))).toEqual([2, 2, 0, 0])
  })
})

describe('waveformPeaks', () => {
  it('downsamples into abs-max buckets', () => {
    const buf = fakeBuffer([[0, 0.2, -0.9, 0.1, 0.05, -0.05, 0.3, -0.3]])
    const peaks = waveformPeaks(buf, 2)
    expect(peaks.length).toBe(2)
    expect(peaks[0]).toBeCloseTo(0.9)   // first half's loudest sample
    expect(peaks[1]).toBeCloseTo(0.3)   // second half's loudest sample
  })

  it('is all zero for silence', () => {
    const buf = fakeBuffer([[0, 0, 0, 0]])
    const peaks = waveformPeaks(buf, 4)
    expect(Array.from(peaks)).toEqual([0, 0, 0, 0])
  })

  it('handles an empty buffer without dividing by zero', () => {
    const buf = fakeBuffer([[]])
    const peaks = waveformPeaks(buf, 8)
    expect(peaks.length).toBe(8)
    expect(Array.from(peaks).every(v => v === 0)).toBe(true)
  })

  it('handles a zero bucket count', () => {
    const buf = fakeBuffer([[1, 2, 3]])
    expect(waveformPeaks(buf, 0).length).toBe(0)
  })
})
