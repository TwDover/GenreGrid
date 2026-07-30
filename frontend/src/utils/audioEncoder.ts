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
/**
 * Encode a rendered AudioBuffer to the user's chosen delivery format.
 *
 * WAV stays synchronous and dependency-free (the sibling wavEncoder). MP3/OGG
 * are produced renderer-side by `wasm-media-encoders`, whose convenience
 * `createMp3Encoder`/`createOggEncoder` inline the LAME / Vorbis WASM as a
 * base64 data URI — so encoding is fully self-contained (no CDN, no network),
 * which matters both for the offline Electron build and the strict-CSP browser
 * build. The module is dynamically imported so its ~0.6 MB of WASM only loads
 * when someone actually exports a compressed file.
 */
import { encodeWav } from './wavEncoder'

export type AudioFormat = 'wav' | 'mp3' | 'ogg'

export const FORMAT_MIME: Record<AudioFormat, string> = {
  wav: 'audio/wav',
  mp3: 'audio/mpeg',
  ogg: 'audio/ogg',
}

// File extension per format (also the label the UI shows on the toggle).
export const FORMAT_EXT: Record<AudioFormat, string> = { wav: 'wav', mp3: 'mp3', ogg: 'ogg' }

export const AUDIO_FORMATS: AudioFormat[] = ['wav', 'mp3', 'ogg']

export async function encodeAudio(buffer: AudioBuffer, format: AudioFormat): Promise<Blob> {
  if (format === 'wav') return encodeWav(buffer)

  const { createMp3Encoder, createOggEncoder } = await import('wasm-media-encoders')
  const encoder = format === 'mp3' ? await createMp3Encoder() : await createOggEncoder()

  const channels = (buffer.numberOfChannels > 1 ? 2 : 1) as 1 | 2
  const sampleRate = buffer.sampleRate
  encoder.configure(
    format === 'mp3'
      // VBR quality 2 ≈ ~190 kbps average — transparent for a share-a-track file.
      ? { channels, sampleRate, vbrQuality: 2 }
      // Vorbis quality 5 ≈ ~160 kbps — the usual "good" OGG setting.
      : { channels, sampleRate, vbrQuality: 5 },
  )

  const left = buffer.getChannelData(0)
  const right = channels === 2 ? buffer.getChannelData(1) : left

  // Feed the encoder in blocks so a multi-minute render never allocates the
  // whole PCM stream twice. `encode()` returns a Uint8Array that VIEWS the
  // encoder's WASM heap and is invalidated on the next call — so each chunk
  // must be copied (`.slice()`) before we continue. 1152 is LAME's frame size;
  // a multiple of it keeps the encoder on frame boundaries.
  const BLOCK = 1152 * 64
  const chunks: Uint8Array[] = []
  for (let i = 0; i < buffer.length; i += BLOCK) {
    const end = Math.min(buffer.length, i + BLOCK)
    const frame = channels === 2
      ? [left.subarray(i, end), right.subarray(i, end)]
      : [left.subarray(i, end)]
    const out = encoder.encode(frame)
    if (out.length) chunks.push(out.slice())
  }
  const tail = encoder.finalize()
  if (tail.length) chunks.push(tail.slice())

  return new Blob(chunks as BlobPart[], { type: FORMAT_MIME[format] })
}
