/*
 * GenreGrid — a style-based MIDI generator.
 * Copyright (C) 2026 Tw Dover
 *
 * This program is free software: you can redistribute it and/or modify it under
 * the terms of the GNU General Public License v3 or (at your option) any later
 * version. Distributed WITHOUT ANY WARRANTY. See <https://www.gnu.org/licenses/>.
 */
// Pure monophonic pitch detection + note segmentation for roadmap 8.2
// (hum/whistle → hook). No Web Audio / DOM dependency — this operates on plain
// Float32Array sample data, so it's unit-testable with synthesized tones and
// reusable from both a live mic tap and an offline AudioBuffer. The YIN
// algorithm (de Cheveigné & Kawahara 2002) is used because it's the standard
// choice for monophonic voice/hum pitch tracking: robust to the breathy,
// harmonic-poor signal a human voice produces, unlike simple autocorrelation
// which tends to octave-jump on it.

/** One analysis frame's result. `frequency` is null when the frame is
 *  unvoiced/silent (no clear periodicity found). `clarity` is 0..1, higher
 *  means a cleaner periodic match (1 - the YIN dip at the chosen lag). */
export interface PitchFrame {
  time: number
  frequency: number | null
  clarity: number
  /** Root-mean-square amplitude of the frame's raw samples — loudness, not
   *  pitch-related, kept alongside it so a note's velocity can be derived
   *  from how the phrase was actually performed. */
  rms: number
}

/** A segmented note: constant (median) pitch across a stable voiced span. */
export interface DetectedNote {
  midi: number
  startSec: number
  durationSec: number
  /** 0..1, from the span's average signal RMS relative to the loudest frame
   *  in the whole take — a hummed accent reads as a higher velocity. */
  velocity: number
}

// ── Core YIN single-frame estimator ──────────────────────────────────────────

/** YIN's cumulative mean normalized difference function over `frame`, sized
 *  `frame.length / 2` (a lag needs a full second window to compare against,
 *  so only the first half of the frame yields valid lags). */
function cmndf(frame: Float32Array): Float32Array {
  const half = Math.floor(frame.length / 2)
  const d = new Float32Array(half)
  for (let tau = 1; tau < half; tau++) {
    let sum = 0
    for (let i = 0; i < half; i++) {
      const delta = frame[i] - frame[i + tau]
      sum += delta * delta
    }
    d[tau] = sum
  }
  d[0] = 1
  let runningSum = 0
  for (let tau = 1; tau < half; tau++) {
    runningSum += d[tau]
    d[tau] = runningSum > 0 ? (d[tau] * tau) / runningSum : 1
  }
  return d
}

/** First lag whose normalized difference dips below `threshold`, walked
 *  forward to its local minimum (YIN's own recommended refinement — the
 *  first dip under threshold isn't always the true minimum). -1 if the
 *  signal never dips below threshold (no clear pitch). */
function absoluteThreshold(d: Float32Array, threshold: number): number {
  for (let tau = 2; tau < d.length; tau++) {
    if (d[tau] < threshold) {
      while (tau + 1 < d.length && d[tau + 1] < d[tau]) tau++
      return tau
    }
  }
  return -1
}

/** Parabolic interpolation around `tau` using its two neighbors, for
 *  sub-sample lag precision (otherwise pitch is quantized to whole-sample
 *  lags, which is audibly out of tune at higher frequencies). */
function refineTau(d: Float32Array, tau: number): number {
  const x0 = tau > 0 ? tau - 1 : tau
  const x2 = tau + 1 < d.length ? tau + 1 : tau
  if (x0 === tau || x2 === tau) return tau
  const s0 = d[x0], s1 = d[tau], s2 = d[x2]
  const denom = s0 + s2 - 2 * s1
  if (denom === 0) return tau
  return tau + (s0 - s2) / (2 * denom)
}

/** Estimate the fundamental frequency of one analysis frame via YIN.
 *  Returns null when no lag clears the confidence threshold (silence,
 *  noise, or a non-periodic signal). `threshold` is YIN's own dip
 *  threshold (default 0.15, the value from the original paper). */
export function yinPitch(frame: Float32Array, sampleRate: number,
  threshold = 0.15): { frequency: number; clarity: number } | null {
  if (frame.length < 8) return null
  const d = cmndf(frame)
  const tau = absoluteThreshold(d, threshold)
  if (tau <= 0) return null
  const refined = refineTau(d, tau)
  if (refined <= 0) return null
  const frequency = sampleRate / refined
  const clarity = 1 - Math.min(1, Math.max(0, d[tau]))
  return { frequency, clarity }
}

// ── Frame-by-frame tracking over a full buffer ───────────────────────────────

export interface TrackPitchOptions {
  /** Analysis window in samples (must be >= ~2x the longest period you want
   *  to resolve; 2048 @ 44.1kHz resolves down to ~43Hz, well under any
   *  hummed note). */
  windowSize?: number
  /** Samples between successive frames; smaller = finer time resolution. */
  hopSize?: number
  threshold?: number
}

function frameRms(frame: Float32Array): number {
  let sum = 0
  for (let i = 0; i < frame.length; i++) sum += frame[i] * frame[i]
  return Math.sqrt(sum / frame.length)
}

/** Run YIN across `samples` in overlapping windows, producing a pitch
 *  contour. `sampleRate` must match the buffer (no resampling here). */
export function trackPitch(samples: Float32Array, sampleRate: number,
  opts: TrackPitchOptions = {}): PitchFrame[] {
  const windowSize = opts.windowSize ?? 2048
  const hopSize = opts.hopSize ?? 512
  const threshold = opts.threshold ?? 0.15
  const frames: PitchFrame[] = []
  for (let start = 0; start + windowSize <= samples.length; start += hopSize) {
    const frame = samples.subarray(start, start + windowSize)
    const result = yinPitch(frame, sampleRate, threshold)
    frames.push({
      time: start / sampleRate,
      frequency: result?.frequency ?? null,
      clarity: result?.clarity ?? 0,
      rms: frameRms(frame),
    })
  }
  return frames
}

// ── Note segmentation ────────────────────────────────────────────────────────

/** Hz → fractional MIDI note number (69 = A4 = 440Hz). */
export function frequencyToMidi(frequency: number): number {
  return 69 + 12 * Math.log2(frequency / 440)
}

export interface SegmentNotesOptions {
  /** Minimum clarity for a frame to count as voiced. */
  clarityThreshold?: number
  /** A pitch move bigger than this (semitones) from the current note's
   *  running median starts a new note instead of extending it — lets small
   *  vibrato ride through while still catching a genuine pitch change. */
  semitoneJump?: number
  /** Notes shorter than this are dropped as transient blips (breath noise,
   *  attack transients before pitch settles). */
  minDurationSec?: number
}

/** Group a pitch contour into discrete notes: a run of voiced frames whose
 *  pitch stays within `semitoneJump` of the run's median becomes one note at
 *  that median pitch (rounded to the nearest semitone); unvoiced frames or a
 *  bigger jump break the run. This is the "note segmentation" step between
 *  raw pitch tracking and quantizing to a rhythmic grid. */
export function segmentNotes(frames: PitchFrame[],
  opts: SegmentNotesOptions = {}): DetectedNote[] {
  const clarityThreshold = opts.clarityThreshold ?? 0.85
  const semitoneJump = opts.semitoneJump ?? 0.8
  const minDurationSec = opts.minDurationSec ?? 0.08
  if (frames.length === 0) return []
  const hop = frames.length > 1 ? frames[1].time - frames[0].time : 0

  const maxRms = Math.max(1e-6, ...frames.map(f => f.rms))
  const notes: DetectedNote[] = []
  let run: { midis: number[]; rmsValues: number[]; startTime: number } | null = null

  const flush = (endTime: number) => {
    if (!run) return
    const sorted = [...run.midis].sort((a, b) => a - b)
    const median = sorted[Math.floor(sorted.length / 2)]
    const duration = endTime - run.startTime
    if (duration >= minDurationSec) {
      const avgRms = run.rmsValues.reduce((s, v) => s + v, 0) / run.rmsValues.length
      const velocity = Math.min(1, Math.max(0.3, avgRms / maxRms))
      notes.push({ midi: Math.round(median), startSec: run.startTime, durationSec: duration, velocity })
    }
    run = null
  }

  for (const f of frames) {
    const voiced = f.frequency !== null && f.clarity >= clarityThreshold
    if (!voiced) {
      flush(f.time)
      continue
    }
    const midi = frequencyToMidi(f.frequency as number)
    if (!run) {
      run = { midis: [midi], rmsValues: [f.rms], startTime: f.time }
      continue
    }
    const sorted = [...run.midis].sort((a, b) => a - b)
    const runningMedian = sorted[Math.floor(sorted.length / 2)]
    if (Math.abs(midi - runningMedian) > semitoneJump) {
      flush(f.time)
      run = { midis: [midi], rmsValues: [f.rms], startTime: f.time }
    } else {
      run.midis.push(midi)
      run.rmsValues.push(f.rms)
    }
  }
  flush(frames[frames.length - 1].time + hop)

  return notes
}

// ── Quantization to a rhythmic grid ──────────────────────────────────────────

export interface QuantizedNote {
  pitch: number
  /** In beats, matching the backend's NoteEvent unit. */
  start: number
  duration: number
  velocity: number
}

/** Snap detected notes (seconds) onto a `division`-beat grid at `bpm` and
 *  convert to beats. A note is trimmed if quantizing would make it run into
 *  the next note's (quantized) start — otherwise two close notes can end up
 *  overlapping after independently rounding. */
export function quantizeNotesToBeats(notes: DetectedNote[], bpm: number,
  division = 0.25): QuantizedNote[] {
  const secondsPerBeat = 60 / bpm
  const gridSec = division * secondsPerBeat
  if (gridSec <= 0 || notes.length === 0) return []
  const starts = notes.map(n => Math.round(n.startSec / gridSec) * gridSec)
  return notes.map((n, i) => {
    const startSec = starts[i]
    const nextStart = i + 1 < starts.length ? starts[i + 1] : Infinity
    const roundedDur = Math.max(gridSec, Math.round(n.durationSec / gridSec) * gridSec)
    const cap = nextStart - startSec
    const durSec = cap > 0 && cap < roundedDur ? cap : roundedDur
    return {
      pitch: n.midi,
      start: startSec / secondsPerBeat,
      duration: durSec / secondsPerBeat,
      velocity: Math.round(n.velocity * 127),
    }
  })
}
