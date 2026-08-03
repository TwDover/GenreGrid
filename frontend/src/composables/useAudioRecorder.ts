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
 * Mic/line-in capture for recorded audio clips (roadmap 9.4). Wraps Tone's
 * `UserMedia` (getUserMedia) + `Recorder` (MediaRecorder) — the same pair
 * Tone.js's own examples use for mic recording — so capture lives on the
 * existing Tone audio graph rather than a separate raw Web Audio path.
 *
 * This composable only owns CAPTURE: getting a take out as a fitted
 * AudioBuffer. Count-in, starting song/loop playback for the performer to
 * play along with, and where the clip lands are the caller's job (mirrors
 * PianoRollEditor.vue's MIDI recording, which is deliberately structured the
 * same way — this composable is the audio equivalent of its onMidiNote tap).
 */
import { ref } from 'vue'
import * as Tone from 'tone'
import { fitBufferToDuration } from '../utils/audioClip'

let mic: Tone.UserMedia | null = null
let recorder: Tone.Recorder | null = null
let monitorGain: Tone.Gain | null = null
let levelMeter: Tone.Meter | null = null

function cleanup(): void {
  mic?.close()
  mic?.dispose()
  mic = null
  recorder?.dispose()
  recorder = null
  monitorGain?.dispose()
  monitorGain = null
  levelMeter?.dispose()
  levelMeter = null
}

export function useAudioRecorder() {
  const isRecording = ref(false)
  const monitoring = ref(false)
  const error = ref<string | null>(null)

  /** Audio input devices, for a picker — there's no way to know which one
   *  getUserMedia's default actually is, so a wrong-device take can otherwise
   *  record clean silence with no error at all. Labels are blank until
   *  permission has been granted at least once (browser privacy); callers
   *  should fall back to "Microphone N" using the array index until then. */
  async function listInputDevices(): Promise<MediaDeviceInfo[]> {
    return Tone.UserMedia.enumerateDevices()
  }

  /** Open the mic and start capturing. `deviceId` picks a specific input
   *  (from `listInputDevices`); omitted, the browser/OS default is used.
   *  Throws (and sets `error`) if permission is denied or no input device
   *  is available. */
  async function start(deviceId?: string): Promise<void> {
    if (isRecording.value) return
    error.value = null
    await Tone.start()
    mic = new Tone.UserMedia()
    try {
      await mic.open(deviceId)
    } catch {
      mic.dispose()
      mic = null
      error.value = 'Microphone unavailable — check permission and that an input device is connected.'
      throw new Error(error.value)
    }
    recorder = new Tone.Recorder()
    monitorGain = new Tone.Gain(monitoring.value ? 1 : 0).toDestination()
    levelMeter = new Tone.Meter({ normalRange: true })
    mic.connect(recorder)
    mic.connect(monitorGain)
    mic.connect(levelMeter)
    recorder.start()
    isRecording.value = true
  }

  /** Current input level, 0..1 — poll this (e.g. on a rAF/interval) to show a
   *  live meter while armed/recording, so a wrong or silent device is obvious
   *  BEFORE a whole take is wasted rather than after reviewing it. 0 if not
   *  currently recording. */
  function getLevel(): number {
    if (!levelMeter) return 0
    const v = levelMeter.getValue()
    return Array.isArray(v) ? Math.max(0, ...v) : Math.max(0, v)
  }

  /** Stop capturing and return the raw take (a compressed container blob —
   *  decode via `decodeAndFit` before use). */
  async function stop(): Promise<Blob> {
    if (!isRecording.value || !recorder) throw new Error('Not recording')
    const blob = await recorder.stop()
    isRecording.value = false
    cleanup()
    return blob
  }

  /** Abandon the current take without returning it (e.g. Discard). */
  function cancel(): void {
    if (recorder && isRecording.value) recorder.stop().catch(() => {})
    isRecording.value = false
    cleanup()
  }

  /** Hear your own input while recording (a small live pass-through gain).
   *  Off by default — enabling it over speakers (not headphones) risks
   *  feedback howl, so this is an explicit opt-in, not automatic. */
  function setMonitoring(on: boolean): void {
    monitoring.value = on
    if (monitorGain) monitorGain.gain.value = on ? 1 : 0
  }

  /** Decode a captured take and trim/pad it to EXACTLY `targetSeconds` (see
   *  `fitBufferToDuration`), ready to encode (e.g. via `encodeWav`) and save. */
  async function decodeAndFit(blob: Blob, targetSeconds: number): Promise<AudioBuffer> {
    const ctx = Tone.getContext().rawContext as AudioContext
    const decoded = await ctx.decodeAudioData(await blob.arrayBuffer())
    const fitted = fitBufferToDuration(decoded, targetSeconds)
    const out = new AudioBuffer({
      length: fitted.length, numberOfChannels: fitted.numberOfChannels, sampleRate: fitted.sampleRate,
    })
    fitted.channels.forEach((data, i) => out.copyToChannel(data, i))
    return out
  }

  return { isRecording, monitoring, error, start, stop, cancel, setMonitoring, decodeAndFit, listInputDevices, getLevel }
}
