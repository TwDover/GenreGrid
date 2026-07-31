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
import { ref } from 'vue'
import * as Tone from 'tone'

// ── Pure meter math (unit-tested) ────────────────────────────────────────────
/** The accented beat is the first of each bar. */
export function isDownbeat(beatIndex: number, beatsPerBar: number): boolean {
  return beatsPerBar > 0 ? ((beatIndex % beatsPerBar) + beatsPerBar) % beatsPerBar === 0 : beatIndex === 0
}

/** Transport interval string for one beat of a meter with the given denominator
 *  (4→'4n' quarter, 8→'8n' eighth, …) — the unit the metronome clicks. */
export function clickInterval(denom: number): string {
  return `${denom > 0 ? denom : 4}n`
}

/** Which beat index (0-based) a tick count lands on, for a `/denom` meter. A beat
 *  is a `denom`-note, i.e. PPQ·4/denom ticks (quarter = PPQ, eighth = PPQ/2). */
export function beatIndexAtTicks(ticks: number, ppq: number, denom: number): number {
  const ticksPerBeat = ppq * 4 / (denom > 0 ? denom : 4)
  return Math.round(ticks / ticksPerBeat)
}

/** Seconds of one count-in (all its bars of beats) at a quarter-note tempo. */
export function countInDurationSec(bars: number, beatsPerBar: number, denom: number, bpm: number): number {
  if (bars <= 0 || bpm <= 0) return 0
  const secPerBeat = (60 / bpm) * (4 / (denom > 0 ? denom : 4))
  return bars * beatsPerBar * secPerBeat
}

// ── Persisted state (one metronome across the app) ───────────────────────────
function _lsBool(k: string, d: boolean): boolean {
  try { const v = localStorage.getItem(k); return v === null ? d : v === '1' } catch { return d }
}
function _lsNum(k: string, d: number): number {
  try { const v = localStorage.getItem(k); const n = Number(localStorage.getItem(k)); return v === null || isNaN(n) ? d : n } catch { return d }
}

const enabled = ref(_lsBool('gg_metronome', false))     // ongoing click during playback
const countInBars = ref(_lsNum('gg_countin', 0))         // 0 = off, else 1 or 2 bars
const meterNum = ref(4)                                   // beats per bar (numerator)
const meterDenom = ref(4)                                 // beat unit (denominator)

let clickSynth: Tone.Synth | null = null
let repeatId: number | null = null

function ensureClick(): Tone.Synth {
  if (!clickSynth) {
    // A short triangle blip straight to the destination — a monitoring aid, so it's
    // outside the mix buses and never part of the offline-rendered export.
    clickSynth = new Tone.Synth({
      oscillator: { type: 'triangle' },
      envelope: { attack: 0.001, decay: 0.035, sustain: 0, release: 0.02 },
      volume: -5,
    }).toDestination()
  }
  return clickSynth
}

function playClick(time: number, accent: boolean): void {
  ensureClick().triggerAttackRelease(accent ? 'C7' : 'C6', 0.02, time, accent ? 1 : 0.55)
}

/** (Re)schedule the click on the running transport. No-op when disabled. Must be
 *  called AFTER the transport starts (the play path cancels events on each new play). */
function startTicking(): void {
  stopTicking()
  if (!enabled.value) return
  ensureClick()
  const tr = Tone.getTransport()
  repeatId = tr.scheduleRepeat((time) => {
    const beat = beatIndexAtTicks(tr.getTicksAtTime(time), tr.PPQ, meterDenom.value)
    playClick(time, isDownbeat(beat, meterNum.value))
  }, clickInterval(meterDenom.value), 0)
}

function stopTicking(): void {
  if (repeatId !== null) { Tone.getTransport().clear(repeatId); repeatId = null }
}

/** Play `countInBars` bars of clicks starting now; resolve when done, returning the
 *  lead-in duration in seconds (0 if off). Used before a play or a recording. */
async function countIn(): Promise<number> {
  if (countInBars.value <= 0) return 0
  await Tone.start()
  ensureClick()
  const secPerBeat = (60 / Tone.getTransport().bpm.value) * (4 / meterDenom.value)
  const totalBeats = countInBars.value * meterNum.value
  const start = Tone.now()
  for (let i = 0; i < totalBeats; i++) playClick(start + i * secPerBeat, isDownbeat(i, meterNum.value))
  const dur = totalBeats * secPerBeat
  return new Promise(res => setTimeout(() => res(dur), Math.ceil(dur * 1000)))
}

/** Run the transport just for the click (nothing else loaded) — the practice/idle mode. */
async function startStandalone(): Promise<void> {
  await Tone.start()
  ensureClick()
  const tr = Tone.getTransport()
  tr.loop = false
  tr.seconds = 0
  startTicking()
  tr.start()
}
function stopStandalone(): void {
  stopTicking()
  Tone.getTransport().stop()
}

function setEnabled(v: boolean): void {
  enabled.value = v
  try { localStorage.setItem('gg_metronome', v ? '1' : '0') } catch { /* storage unavailable */ }
}
function setCountInBars(n: number): void {
  countInBars.value = n
  try { localStorage.setItem('gg_countin', String(n)) } catch { /* storage unavailable */ }
}
/** Set the click grid from the loaded track's time signature (default 4/4). */
function setMeter(num: number, denom: number): void {
  if (num > 0) meterNum.value = Math.round(num)
  if (denom > 0) meterDenom.value = Math.round(denom)
}

// Named exports so the player can drive ticking without instantiating the composable.
export { startTicking, stopTicking, countIn, setMeter }

export function useMetronome() {
  return {
    enabled, countInBars, meterNum, meterDenom,
    setEnabled, setCountInBars, setMeter,
    startTicking, stopTicking, countIn, startStandalone, stopStandalone,
  }
}
