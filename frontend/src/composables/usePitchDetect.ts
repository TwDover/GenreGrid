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
 * Hum/whistle → melody (roadmap 8.2). Wraps `useAudioRecorder`'s mic capture
 * with offline pitch detection: stop a take, decode it, run it through
 * `pitchDetect.ts` (YIN + note segmentation + grid quantization), and hand
 * back a note list ready to POST to /build-song-from-notes. Detection itself
 * is pure/unit-tested in pitchDetect.ts — this composable only wires that to
 * the browser's audio decode step, mirroring how useAudioRecorder separates
 * pure capture from PianoRollEditor's MIDI-recording orchestration.
 */
import { ref } from 'vue'
import * as Tone from 'tone'
import { useAudioRecorder } from './useAudioRecorder'
import { trackPitch, segmentNotes, quantizeNotesToBeats, type QuantizedNote } from '../utils/pitchDetect'

export function usePitchDetect() {
  const recorder = useAudioRecorder()
  const processing = ref(false)
  const notes = ref<QuantizedNote[]>([])
  const detectError = ref<string | null>(null)

  function reset() {
    notes.value = []
    detectError.value = null
  }

  async function start(deviceId?: string): Promise<void> {
    reset()
    await recorder.start(deviceId)
  }

  function cancel(): void {
    recorder.cancel()
    reset()
  }

  /** Stop capture, pitch-detect the take, and quantize to `bpm`. Returns the
   *  detected notes (also left in `notes` for the caller to preview); throws
   *  via `detectError` (not an exception) when too little usable melody was
   *  found, since that's an expected outcome of a bad take, not a bug. */
  async function stopAndDetect(bpm: number): Promise<QuantizedNote[]> {
    const blob = await recorder.stop()
    processing.value = true
    try {
      const ctx = Tone.getContext().rawContext as AudioContext
      const decoded = await ctx.decodeAudioData(await blob.arrayBuffer())
      const samples = decoded.getChannelData(0)
      const frames = trackPitch(samples, decoded.sampleRate)
      const detected = segmentNotes(frames)
      if (detected.length < 4) {
        detectError.value = 'Could not find a clear melody in that take — try humming a bit louder and slower, closer to the mic.'
        notes.value = []
        return []
      }
      detectError.value = null
      const quantized = quantizeNotesToBeats(detected, bpm)
      notes.value = quantized
      return quantized
    } finally {
      processing.value = false
    }
  }

  return {
    isRecording: recorder.isRecording,
    monitoring: recorder.monitoring,
    recordError: recorder.error,
    processing,
    notes,
    detectError,
    listInputDevices: recorder.listInputDevices,
    getLevel: recorder.getLevel,
    setMonitoring: recorder.setMonitoring,
    start,
    cancel,
    stopAndDetect,
    reset,
  }
}
