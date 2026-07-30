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
import { encodeAudio, FORMAT_MIME, FORMAT_EXT, AUDIO_FORMATS } from './audioEncoder'

// Minimal AudioBuffer stand-in — the encoders only read these four members, and
// jsdom has no real Web Audio. A short sine keeps the WASM encode fast.
function fakeBuffer(seconds = 0.1, sampleRate = 44100, channels = 2): AudioBuffer {
  const n = Math.round(seconds * sampleRate)
  const data = Array.from({ length: channels }, (_, c) => {
    const a = new Float32Array(n)
    for (let i = 0; i < n; i++) a[i] = 0.3 * Math.sin((2 * Math.PI * (440 + c * 55) * i) / sampleRate)
    return a
  })
  return {
    numberOfChannels: channels,
    sampleRate,
    length: n,
    getChannelData: (c: number) => data[c],
  } as unknown as AudioBuffer
}

async function magic(blob: Blob, len: number): Promise<number[]> {
  return [...new Uint8Array(await blob.slice(0, len).arrayBuffer())]
}

describe('audioEncoder', () => {
  it('exposes the three formats with matching mime/ext maps', () => {
    expect(AUDIO_FORMATS).toEqual(['wav', 'mp3', 'ogg'])
    for (const f of AUDIO_FORMATS) {
      expect(FORMAT_MIME[f]).toBeTruthy()
      expect(FORMAT_EXT[f]).toBeTruthy()
    }
  })

  it('encodes WAV synchronously via the sibling encoder', async () => {
    const blob = await encodeAudio(fakeBuffer(), 'wav')
    expect(blob.type).toBe('audio/wav')
    expect(await magic(blob, 4)).toEqual([...'RIFF'].map(c => c.charCodeAt(0)))
  })

  it('encodes a valid MP3 (frame-sync header, audio/mpeg blob)', async () => {
    const blob = await encodeAudio(fakeBuffer(), 'mp3')
    expect(blob.type).toBe('audio/mpeg')
    expect(blob.size).toBeGreaterThan(0)
    // MPEG audio frames begin with an 11-bit sync word (0xFFE...).
    const [b0, b1] = await magic(blob, 2)
    expect(b0).toBe(0xff)
    expect(b1 & 0xe0).toBe(0xe0)
  })

  it('encodes a valid OGG Vorbis (OggS capture pattern, audio/ogg blob)', async () => {
    const blob = await encodeAudio(fakeBuffer(), 'ogg')
    expect(blob.type).toBe('audio/ogg')
    expect(blob.size).toBeGreaterThan(0)
    expect(await magic(blob, 4)).toEqual([...'OggS'].map(c => c.charCodeAt(0)))
  })

  it('encodes a mono buffer to MP3 without error', async () => {
    const blob = await encodeAudio(fakeBuffer(0.1, 44100, 1), 'mp3')
    expect(blob.type).toBe('audio/mpeg')
    expect(blob.size).toBeGreaterThan(0)
  })
})
