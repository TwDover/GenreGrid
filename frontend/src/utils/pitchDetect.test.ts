/*
 * GenreGrid — a style-based MIDI generator.
 * Copyright (C) 2026 Tw Dover
 *
 * This program is free software: you can redistribute it and/or modify it under
 * the terms of the GNU General Public License v3 or (at your option) any later
 * version. Distributed WITHOUT ANY WARRANTY. See <https://www.gnu.org/licenses/>.
 */
// Spike validation (roadmap 8.2): before any recording UI exists, prove the
// YIN detector + segmenter are accurate on messy signals, not just clean
// tones — a hummed take has noise, vibrato, and imperfect onsets, and that's
// the whole risk the roadmap flags for this feature.
import { describe, it, expect } from 'vitest'
import {
  yinPitch, trackPitch, segmentNotes, frequencyToMidi, quantizeNotesToBeats,
  type PitchFrame, type DetectedNote,
} from './pitchDetect'

const SR = 44100

function sineWave(freq: number, durationSec: number, sampleRate = SR, amplitude = 0.5): Float32Array {
  const n = Math.round(durationSec * sampleRate)
  const out = new Float32Array(n)
  for (let i = 0; i < n; i++) out[i] = amplitude * Math.sin((2 * Math.PI * freq * i) / sampleRate)
  return out
}

// Deterministic pseudo-noise (no RNG import needed) so tests are reproducible.
function mulberry32(seed: number) {
  return () => {
    seed |= 0; seed = (seed + 0x6d2b79f5) | 0
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

function addNoise(signal: Float32Array, amount: number, seed = 1): Float32Array {
  const rand = mulberry32(seed)
  const out = new Float32Array(signal.length)
  for (let i = 0; i < signal.length; i++) out[i] = signal[i] + amount * (rand() * 2 - 1)
  return out
}

function whiteNoise(n: number, amplitude = 0.5, seed = 1): Float32Array {
  const rand = mulberry32(seed)
  const out = new Float32Array(n)
  for (let i = 0; i < n; i++) out[i] = amplitude * (rand() * 2 - 1)
  return out
}

describe('yinPitch — single frame', () => {
  it('detects a clean 220Hz tone (A3, typical low-hum range) within 1%', () => {
    const frame = sineWave(220, 2048 / SR)
    const result = yinPitch(frame, SR)
    expect(result).not.toBeNull()
    expect(result!.frequency).toBeCloseTo(220, 0)
    expect(Math.abs(result!.frequency - 220) / 220).toBeLessThan(0.01)
    expect(result!.clarity).toBeGreaterThan(0.9)
  })

  it('detects a clean 440Hz tone within 1%', () => {
    const frame = sineWave(440, 2048 / SR)
    const result = yinPitch(frame, SR)
    expect(result).not.toBeNull()
    expect(Math.abs(result!.frequency - 440) / 440).toBeLessThan(0.01)
  })

  it('detects a whistled-range 1000Hz tone within 1%', () => {
    const frame = sineWave(1000, 2048 / SR)
    const result = yinPitch(frame, SR)
    expect(result).not.toBeNull()
    expect(Math.abs(result!.frequency - 1000) / 1000).toBeLessThan(0.02)
  })

  it('stays close under moderate noise (real mic input is never a pure tone)', () => {
    const frame = addNoise(sineWave(330, 2048 / SR, SR, 0.6), 0.08, 42)
    const result = yinPitch(frame, SR)
    expect(result).not.toBeNull()
    expect(Math.abs(result!.frequency - 330) / 330).toBeLessThan(0.03)
  })

  it('returns null on silence', () => {
    const frame = new Float32Array(2048)
    expect(yinPitch(frame, SR)).toBeNull()
  })

  it('returns null (or very low clarity) on pure white noise', () => {
    const frame = whiteNoise(2048, 0.5, 7)
    const result = yinPitch(frame, SR)
    if (result) expect(result.clarity).toBeLessThan(0.85)
  })
})

describe('frequencyToMidi', () => {
  it('maps A4 (440Hz) to MIDI 69 and A3 (220Hz) to MIDI 57', () => {
    expect(frequencyToMidi(440)).toBeCloseTo(69, 5)
    expect(frequencyToMidi(220)).toBeCloseTo(57, 5)
  })
})

describe('trackPitch — full buffer contour', () => {
  it('tracks a two-note buffer (220Hz then 330Hz, silent gap between)', () => {
    const note1 = sineWave(220, 0.4)
    const gap = new Float32Array(Math.round(0.1 * SR))
    const note2 = sineWave(330, 0.4)
    const buffer = new Float32Array(note1.length + gap.length + note2.length)
    buffer.set(note1, 0)
    buffer.set(gap, note1.length)
    buffer.set(note2, note1.length + gap.length)

    const frames = trackPitch(buffer, SR)
    const firstHalf = frames.filter(f => f.time < 0.35 && f.frequency !== null)
    const secondHalf = frames.filter(f => f.time > 0.55 && f.frequency !== null)
    expect(firstHalf.length).toBeGreaterThan(5)
    expect(secondHalf.length).toBeGreaterThan(5)
    const avg = (arr: PitchFrame[]) => arr.reduce((s, f) => s + (f.frequency ?? 0), 0) / arr.length
    expect(avg(firstHalf)).toBeCloseTo(220, -1)
    expect(avg(secondHalf)).toBeCloseTo(330, -1)

    // The silent gap should show up as unvoiced (null) frames.
    const gapFrames = frames.filter(f => f.time > 0.42 && f.time < 0.48)
    expect(gapFrames.some(f => f.frequency === null)).toBe(true)
  })
})

describe('segmentNotes', () => {
  function frame(time: number, frequency: number | null, clarity = 0.95, rms = 0.5): PitchFrame {
    return { time, frequency, clarity, rms }
  }

  it('groups a stable run of frames into one note at the median pitch', () => {
    const frames: PitchFrame[] = []
    for (let i = 0; i < 20; i++) frames.push(frame(i * 0.01, 220))
    const notes = segmentNotes(frames)
    expect(notes).toHaveLength(1)
    expect(notes[0].midi).toBe(57)
    expect(notes[0].startSec).toBeCloseTo(0, 5)
  })

  it('splits on a silent gap into two notes', () => {
    const frames: PitchFrame[] = []
    for (let i = 0; i < 15; i++) frames.push(frame(i * 0.01, 220))
    for (let i = 15; i < 20; i++) frames.push(frame(i * 0.01, null, 0))
    for (let i = 20; i < 35; i++) frames.push(frame(i * 0.01, 330))
    const notes = segmentNotes(frames)
    expect(notes).toHaveLength(2)
    expect(notes[0].midi).toBe(57)
    expect(notes[1].midi).toBe(64)
  })

  it('splits on a big pitch jump even with no silence between (legato hum)', () => {
    const frames: PitchFrame[] = []
    for (let i = 0; i < 15; i++) frames.push(frame(i * 0.01, 220))
    for (let i = 15; i < 30; i++) frames.push(frame(i * 0.01, 330))
    const notes = segmentNotes(frames)
    expect(notes).toHaveLength(2)
  })

  it('rides through small vibrato (±0.3 semitone) as a single note', () => {
    const frames: PitchFrame[] = []
    const baseMidi = 60 // C4
    for (let i = 0; i < 40; i++) {
      const vibrato = 0.3 * Math.sin((2 * Math.PI * 5 * i) / 100) // ~5Hz vibrato, small depth
      const freq = 440 * Math.pow(2, (baseMidi - 69 + vibrato) / 12)
      frames.push(frame(i * 0.01, freq))
    }
    const notes = segmentNotes(frames)
    expect(notes).toHaveLength(1)
    expect(notes[0].midi).toBe(60)
  })

  it('drops sub-minimum-duration blips', () => {
    const frames: PitchFrame[] = [frame(0, 220), frame(0.01, 220)] // 10ms, well under 80ms default
    const notes = segmentNotes(frames)
    expect(notes).toHaveLength(0)
  })

  it('ignores low-clarity frames even when a frequency is present', () => {
    const frames: PitchFrame[] = []
    for (let i = 0; i < 20; i++) frames.push(frame(i * 0.01, 220, 0.4)) // below default 0.85 threshold
    const notes = segmentNotes(frames)
    expect(notes).toHaveLength(0)
  })

  it('derives velocity from RMS relative to the loudest frame in the take', () => {
    const frames: PitchFrame[] = []
    for (let i = 0; i < 10; i++) frames.push(frame(i * 0.01, 220, 0.95, 0.1))   // quiet note
    for (let i = 10; i < 15; i++) frames.push(frame(i * 0.01, null, 0, 0))     // gap
    for (let i = 15; i < 25; i++) frames.push(frame(i * 0.01, 330, 0.95, 0.5)) // loud note (the take's max)
    const notes = segmentNotes(frames)
    expect(notes).toHaveLength(2)
    expect(notes[1].velocity).toBeCloseTo(1, 5)          // loudest frame in the take -> full velocity
    expect(notes[0].velocity).toBeCloseTo(0.3, 5)         // 0.1 / 0.5 = 0.2, clamped to the 0.3 floor
    expect(notes[0].velocity).toBeLessThan(notes[1].velocity)
  })
})

describe('end-to-end: buffer -> contour -> notes', () => {
  it('recovers a simple three-note hummed phrase (C4, E4, G4) from synthesized audio', () => {
    const c4 = sineWave(261.63, 0.3)
    const e4 = sineWave(329.63, 0.3)
    const g4 = sineWave(392.0, 0.3)
    const gap = new Float32Array(Math.round(0.08 * SR))
    const parts = [c4, gap, e4, gap, g4]
    const total = parts.reduce((s, p) => s + p.length, 0)
    const buffer = new Float32Array(total)
    let offset = 0
    for (const p of parts) { buffer.set(p, offset); offset += p.length }

    const frames = trackPitch(addNoise(buffer, 0.02, 99), SR)
    const notes = segmentNotes(frames)
    const midis = notes.map(n => n.midi)
    expect(midis).toEqual([60, 64, 67]) // C4, E4, G4
  })
})

describe('quantizeNotesToBeats', () => {
  function note(midi: number, startSec: number, durationSec: number, velocity = 0.8): DetectedNote {
    return { midi, startSec, durationSec, velocity }
  }

  it('snaps start/duration to the nearest 16th note and converts seconds to beats', () => {
    // 120bpm -> secondsPerBeat = 0.5, a 16th note = 0.125s
    const notes = [note(60, 0.51, 0.24)] // ~1 beat late by 0.01s, ~2 16ths long by a hair
    const [q] = quantizeNotesToBeats(notes, 120)
    expect(q.pitch).toBe(60)
    expect(q.start).toBeCloseTo(1, 5)       // 0.5s -> beat 1
    expect(q.duration).toBeCloseTo(0.5, 5)  // 0.25s -> half a beat
  })

  it('converts 0..1 velocity to a 0..127 MIDI velocity', () => {
    const [q] = quantizeNotesToBeats([note(60, 0, 0.2, 1)], 120)
    expect(q.velocity).toBe(127)
  })

  it('trims a note that would otherwise overlap the next note after rounding', () => {
    // Two notes 0.13s apart at 120bpm (grid = 0.125s) round to the SAME start —
    // without trimming the first note's rounded duration would swallow the second.
    const notes = [note(60, 0, 0.2), note(64, 0.13, 0.2)]
    const q = quantizeNotesToBeats(notes, 120)
    expect(q[1].start).toBeGreaterThanOrEqual(q[0].start)
    expect(q[0].start + q[0].duration).toBeLessThanOrEqual(q[1].start + 1e-9)
  })

  it('never produces a zero-length note (minimum one grid unit)', () => {
    const [q] = quantizeNotesToBeats([note(60, 0, 0.01)], 120)
    expect(q.duration).toBeGreaterThan(0)
  })
})
