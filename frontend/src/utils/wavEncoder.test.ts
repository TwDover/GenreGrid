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
import { encodeWav } from './wavEncoder'

// Minimal AudioBuffer stand-in — encodeWav only reads these four members, and
// jsdom has no real Web Audio, so a fake exercises the pure encoding maths.
function fakeBuffer(channels: number[][], sampleRate = 44100): AudioBuffer {
  return {
    numberOfChannels: channels.length,
    sampleRate,
    length: channels[0].length,
    getChannelData: (c: number) => Float32Array.from(channels[c]),
  } as unknown as AudioBuffer
}

async function bytesOf(blob: Blob): Promise<DataView> {
  return new DataView(await blob.arrayBuffer())
}

function ascii(v: DataView, off: number, len: number): string {
  let s = ''
  for (let i = 0; i < len; i++) s += String.fromCharCode(v.getUint8(off + i))
  return s
}

describe('encodeWav', () => {
  it('writes a correct 44-byte PCM header for stereo 44.1k', async () => {
    const blob = encodeWav(fakeBuffer([[0, 0, 0], [0, 0, 0]], 44100))
    expect(blob.type).toBe('audio/wav')
    const v = await bytesOf(blob)
    const dataLen = 3 /*frames*/ * 2 /*ch*/ * 2 /*bytes*/
    expect(ascii(v, 0, 4)).toBe('RIFF')
    expect(v.getUint32(4, true)).toBe(36 + dataLen)   // chunk size
    expect(ascii(v, 8, 4)).toBe('WAVE')
    expect(ascii(v, 12, 4)).toBe('fmt ')
    expect(v.getUint32(16, true)).toBe(16)            // fmt size
    expect(v.getUint16(20, true)).toBe(1)             // PCM
    expect(v.getUint16(22, true)).toBe(2)             // channels
    expect(v.getUint32(24, true)).toBe(44100)         // sample rate
    expect(v.getUint32(28, true)).toBe(44100 * 2 * 2) // byte rate
    expect(v.getUint16(32, true)).toBe(2 * 2)         // block align
    expect(v.getUint16(34, true)).toBe(16)            // bits/sample
    expect(ascii(v, 36, 4)).toBe('data')
    expect(v.getUint32(40, true)).toBe(dataLen)
    expect(v.byteLength).toBe(44 + dataLen)
  })

  it('interleaves stereo frames L,R,L,R and scales to int16', async () => {
    // L = [1.0, 0], R = [-1.0, 0]. Full-scale +1 -> 32767, -1 -> -32768.
    const v = await bytesOf(encodeWav(fakeBuffer([[1, 0], [-1, 0]])))
    expect(v.getInt16(44, true)).toBe(32767)   // frame0 L
    expect(v.getInt16(46, true)).toBe(-32768)  // frame0 R
    expect(v.getInt16(48, true)).toBe(0)       // frame1 L
    expect(v.getInt16(50, true)).toBe(0)       // frame1 R
  })

  it('clamps out-of-range samples to the int16 rails', async () => {
    const v = await bytesOf(encodeWav(fakeBuffer([[2.5, -2.5]])))  // mono, over-range
    expect(v.getUint16(22, true)).toBe(1)      // 1 channel in header
    expect(v.getInt16(44, true)).toBe(32767)   // +2.5 clamps to +1 -> max
    expect(v.getInt16(46, true)).toBe(-32768)  // -2.5 clamps to -1 -> min
  })

  it('encodes a mono buffer with the mono byte rate / block align', async () => {
    const v = await bytesOf(encodeWav(fakeBuffer([[0.5, -0.5, 0.25]], 22050)))
    expect(v.getUint16(22, true)).toBe(1)              // channels
    expect(v.getUint32(24, true)).toBe(22050)          // sample rate
    expect(v.getUint32(28, true)).toBe(22050 * 1 * 2)  // byte rate
    expect(v.getUint16(32, true)).toBe(1 * 2)          // block align
    expect(v.getUint32(40, true)).toBe(3 * 1 * 2)      // data length
  })
})
