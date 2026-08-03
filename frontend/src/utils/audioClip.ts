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
 * Pure audio-buffer helpers for recorded clips (roadmap 9.4). Duck-typed
 * against a minimal AudioBuffer shape (mirrors useOfflineRender.ts's
 * sumPartBuffers pattern) so this stays testable with plain objects — no real
 * Web Audio API needed, unlike constructing an actual AudioBuffer/AudioContext.
 */
export interface AudioBufferLike {
  readonly length: number
  readonly sampleRate: number
  readonly numberOfChannels: number
  getChannelData(channel: number): Float32Array<ArrayBuffer>
}

export interface FittedBuffer {
  length: number
  sampleRate: number
  numberOfChannels: number
  channels: Float32Array<ArrayBuffer>[]
}

/**
 * Trim or zero-pad a captured buffer to EXACTLY `targetSeconds`. A clip's
 * placement (start_bar/bars) implies a fixed duration, so every saved clip
 * matches its declared span exactly — no variable-length drift for playback/
 * export placement math to account for. Extra tail samples are dropped; a
 * short take (mic latency, early stop) is padded with silence.
 */
export function fitBufferToDuration(buffer: AudioBufferLike, targetSeconds: number): FittedBuffer {
  const targetLength = Math.max(1, Math.round(targetSeconds * buffer.sampleRate))
  const channels: Float32Array<ArrayBuffer>[] = []
  for (let c = 0; c < buffer.numberOfChannels; c++) {
    const src = buffer.getChannelData(c)
    const out = new Float32Array(targetLength)
    out.set(src.subarray(0, Math.min(src.length, targetLength)))
    channels.push(out)
  }
  return { length: targetLength, sampleRate: buffer.sampleRate, numberOfChannels: buffer.numberOfChannels, channels }
}

/**
 * Place a clip's samples at `offsetSeconds` within a `totalLength`-sample
 * silent buffer (for offline export — see useOfflineRender.ts's
 * `sumPartBuffers`, which this is shaped to feed directly alongside the
 * per-part renders). Samples that would fall at or past `totalLength` are
 * dropped rather than wrapped or thrown — a clip recorded right at a song's
 * tail end just doesn't overhang the render.
 */
export function placeClipInMix(
  clip: AudioBufferLike, offsetSeconds: number, totalLength: number,
): AudioBufferLike {
  const offset = Math.max(0, Math.round(offsetSeconds * clip.sampleRate))
  const channels: Float32Array<ArrayBuffer>[] = []
  for (let c = 0; c < clip.numberOfChannels; c++) {
    const out = new Float32Array(totalLength)
    const src = clip.getChannelData(c)
    const copyLen = Math.max(0, Math.min(src.length, totalLength - offset))
    if (copyLen > 0) out.set(src.subarray(0, copyLen), offset)
    channels.push(out)
  }
  return {
    length: totalLength, sampleRate: clip.sampleRate, numberOfChannels: clip.numberOfChannels,
    getChannelData: (c: number) => channels[c],
  }
}

/**
 * Downsample a buffer's first channel into `buckets` peak (abs-max) values
 * for a waveform preview canvas. Silence (or a channel with no samples)
 * yields an all-zero array rather than dividing by zero.
 */
export function waveformPeaks(buffer: AudioBufferLike, buckets: number): Float32Array {
  const out = new Float32Array(Math.max(0, buckets))
  if (buckets <= 0 || buffer.numberOfChannels === 0 || buffer.length === 0) return out
  const data = buffer.getChannelData(0)
  const bucketSize = Math.max(1, Math.floor(data.length / buckets))
  for (let i = 0; i < buckets; i++) {
    const start = i * bucketSize
    const end = i === buckets - 1 ? data.length : Math.min(data.length, start + bucketSize)
    let max = 0
    for (let j = start; j < end; j++) {
      const v = Math.abs(data[j])
      if (v > max) max = v
    }
    out[i] = max
  }
  return out
}
