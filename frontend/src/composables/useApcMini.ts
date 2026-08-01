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

// APC mini mk2 control-surface driver. Attached by useMidiInput's surface slot
// when MIDI input is enabled and an APC mini mk2 is present; the wire protocol
// lives in utils/apcMini.ts (pure + tested), this file is the behavior:
//
//   grid (pads mode)   follows the selected voice: drums → a lit 4×4 drum rack
//                      (bottom-left); chords → an 8×8 chord grid (columns =
//                      scale degrees, rows = octaves, one pad = one diatonic
//                      triad); other melodic voices → an 8×8 note grid in
//                      fourths (Push-style). When an editor supplies key/scale,
//                      the note grid lights in-key pads (roots cyan, scale dim,
//                      out-of-key dark). All play + record through the normal
//                      MIDI-in pipeline
//   grid (steps mode)  8×8 step sequencer over the open drum editor's pattern —
//                      rows are kit lanes, columns are 1/16 steps, the playhead
//                      sweeps in white; track buttons page through longer loops
//   scene buttons      1 play/pause · 2 stop · 3 loop · 4 record ·
//                      5/6 octave up/down (note/chord grid) · 7 metronome ·
//                      8 grid mode
//   track buttons      per-part mutes; SOLO while Shift is held (LEDs show the
//                      soloed part); page select while in steps mode
//   faders             1–7 part levels (velocity mixer) · 8 pad velocity ·
//                      9 master volume
//
// LEDs mirror app state via a ~15 Hz diffed frame render: each tick builds the
// desired state of all 80 LEDs and sends only what changed, so the surface stays
// live (mutes, transport, playhead) without flooding the MIDI port.

import { ref } from 'vue'
import { useMidiPlayer } from './useMidiPlayer'
import { PLAYER_PARTS } from './playerConstants'
import {
  registerSurfaceDriver, dispatchSurfaceNote, surfaceTargetPart, surfaceKeyScale,
  type WebMidiInput, type WebMidiOutput,
} from './useMidiInput'
import { useMetronome } from './useMetronome'
import {
  APC_COLOR, APC_FX, APC_GRID_SIZE, APC_TRACK_BTN_BASE, APC_SCENE_BTN_BASE,
  cellToPad, padLedMsg, buttonLedMsg, blackoutMsgs, parseApcMessage,
  isApcMiniMk1, pickApcPort, rackCellToPitch, drumPadColor,
  noteGridPitch, noteGridBaseFor, diatonicTriad,
} from '../utils/apcMini'
import { scaleIntervals, keyIndex } from '../utils/chordResolver'

// ── Step-sequencer surface (registered by the drum editor while open) ────────
export interface StepSurfaceLane { pitch: number; name: string }
export interface StepSurface {
  /** Kit lanes bottom-row-first (index 0 = the grid's bottom row), max 8. */
  lanes: () => StepSurfaceLane[]
  /** Total 1/16 steps in the editable span. */
  stepCount: () => number
  stepAt: (lane: number, step: number) => boolean
  toggleStep: (lane: number, step: number) => void
  /** Step under the playhead, -1 when stopped. */
  playheadStep: () => number
  recording: () => boolean
  toggleRecord: () => void
}

// ── Shared module state ──────────────────────────────────────────────────────
const connected = ref(false)                       // an APC mini mk2 is attached
const mk1Detected = ref(false)                     // saw an original APC mini (unsupported)
const gridMode = ref<'pads' | 'steps'>('pads')
const page = ref(0)                                // step-sequencer page (8 steps each)
const octaveShift = ref(0)                         // note/chord-grid transpose, in octaves
const padVelocity = ref(0.8)                       // pads aren't velocity-sensitive; fader 8 sets this

let stepSurface: StepSurface | null = null
let output: WebMidiOutput | null = null
let refreshTimer: ReturnType<typeof setInterval> | null = null
let shiftHeld = false                              // Shift layer: track buttons become solo
const heldPads = new Map<number, number[]>()       // pressed pad note → sounding pitches
const lastFrame = new Map<number, string>()        // note → last-sent "status:vel"

// Bottom-left pitch of the note grid for the current voice, octave shift applied,
// clamped so the whole 8×8 (top-right = base + 42) stays inside MIDI range.
function gridBase(part: string): number {
  return Math.max(0, Math.min(127 - 42, noteGridBaseFor(part) + octaveShift.value * 12))
}

// Key/scale for the grid: whatever the audition target carries (the editor sends
// its stem's key), else C major so the chord grid always works.
function gridKey(): { keyIdx: number; intervals: number[]; known: boolean } {
  const ks = surfaceKeyScale()
  return ks
    ? { keyIdx: keyIndex(ks.keyRoot), intervals: scaleIntervals(ks.scale), known: true }
    : { keyIdx: 0, intervals: scaleIntervals('major'), known: false }
}

/** What a pad sounds for the current voice: one drum hit, one grid note, or a
 *  whole diatonic triad on the chords voice. Null = dead pad. */
function padPitches(col: number, row: number, part: string): number[] | null {
  if (part === 'drums') {
    const p = rackCellToPitch(col, row)
    return p === null ? null : [p]
  }
  if (part === 'chords') {
    const k = gridKey()
    return diatonicTriad(col, row, gridBase(part) + k.keyIdx, k.intervals)
  }
  const p = noteGridPitch(col, row, gridBase(part))
  return p === null ? null : [p]
}

/** Release everything still held — layouts shift under the fingers (octave change,
 *  detach), and a moved pad must not leave its old pitch ringing. */
function releaseHeld(): void {
  for (const [, pitches] of heldPads) for (const p of pitches) dispatchSurfaceNote('off', p, 0)
  heldPads.clear()
}

/** The drum editor plugs its pattern in here; returns an unregister. Steps mode
 *  is only reachable while a surface is registered. */
export function registerStepSurface(s: StepSurface): () => void {
  stepSurface = s
  page.value = 0
  return () => {
    if (stepSurface === s) {
      stepSurface = null
      if (gridMode.value === 'steps') gridMode.value = 'pads'
    }
  }
}

// ── LED frame rendering ──────────────────────────────────────────────────────
function sendDiff(note: number, msg: number[]) {
  const key = `${msg[0]}:${msg[2]}`
  if (lastFrame.get(note) === key) return
  lastFrame.set(note, key)
  output?.send(msg)
}

function renderPadsMode() {
  const part = surfaceTargetPart()
  const k = gridKey()
  const inScale = new Set(k.intervals.map(i => (k.keyIdx + i) % 12))
  for (let row = 0; row < APC_GRID_SIZE; row++) {
    for (let col = 0; col < APC_GRID_SIZE; col++) {
      const note = cellToPad(col, row)
      const pitches = padPitches(col, row, part)
      if (pitches === null) { sendDiff(note, padLedMsg(note, APC_COLOR.off)); continue }
      let msg: number[]
      if (heldPads.has(note)) {
        msg = padLedMsg(note, APC_COLOR.white, APC_FX.solid)         // flash while held
      } else if (part === 'drums') {
        msg = padLedMsg(note, drumPadColor(pitches[0]), APC_FX.solid25)   // rack: piece color, dimmed
      } else if (part === 'chords') {
        // Chord grid: tonic columns (I) cyan, other degrees faint.
        msg = col % 7 === 0
          ? padLedMsg(note, APC_COLOR.cyan, APC_FX.solid25)
          : padLedMsg(note, APC_COLOR.dim, APC_FX.solid50)
      } else if (k.known) {
        // In-key note grid: roots cyan, scale tones faint, out-of-key dark
        // (still playable — chromatic layout is unchanged).
        const pc = pitches[0] % 12
        msg = pc === k.keyIdx
          ? padLedMsg(note, APC_COLOR.cyan, APC_FX.solid50)
          : inScale.has(pc)
            ? padLedMsg(note, APC_COLOR.dim, APC_FX.solid50)
            : padLedMsg(note, APC_COLOR.off)
      } else {
        // No key known: light the C's as landmarks, leave the rest faintly visible.
        msg = pitches[0] % 12 === 0
          ? padLedMsg(note, APC_COLOR.cyan, APC_FX.solid25)
          : padLedMsg(note, APC_COLOR.dim, APC_FX.solid50)
      }
      sendDiff(note, msg)
    }
  }
}

function renderStepsMode(s: StepSurface) {
  const lanes = s.lanes()
  const steps = s.stepCount()
  const playhead = s.playheadStep()
  for (let row = 0; row < APC_GRID_SIZE; row++) {
    const lane = lanes[row]
    for (let col = 0; col < APC_GRID_SIZE; col++) {
      const note = cellToPad(col, row)
      const step = page.value * APC_GRID_SIZE + col
      if (!lane || step >= steps) { sendDiff(note, padLedMsg(note, APC_COLOR.off)); continue }
      const on = s.stepAt(row, step)
      const msg = step === playhead
        ? padLedMsg(note, APC_COLOR.white, on ? APC_FX.solid : APC_FX.solid25)   // sweeping column
        : padLedMsg(note, on ? drumPadColor(lane.pitch) : APC_COLOR.off,
            on ? APC_FX.solid : APC_FX.solid10)
      sendDiff(note, msg)
    }
  }
}

function renderButtons() {
  const player = useMidiPlayer()
  const metro = useMetronome()
  const inSteps = gridMode.value === 'steps' && stepSurface
  // Track row: mutes normally; the soloed part while Shift is held; page
  // selector while sequencing.
  for (let i = 0; i < 8; i++) {
    const note = APC_TRACK_BTN_BASE + i
    let state: 0 | 1 | 2 = 0
    if (inSteps && stepSurface) {
      const pages = Math.ceil(stepSurface.stepCount() / APC_GRID_SIZE)
      const playPage = Math.floor(stepSurface.playheadStep() / APC_GRID_SIZE)
      state = i === page.value ? 1 : (i === playPage && i < pages ? 2 : 0)
    } else if (i < PLAYER_PARTS.length) {
      const muted = player.channelMuted.value
      if (shiftHeld) {
        // Solo view: blink the part that is soloed (everything else muted).
        const p = PLAYER_PARTS[i]
        const isSolo = !muted[p] && PLAYER_PARTS.every(o => o === p || muted[o])
        state = isSolo ? 2 : 0
      } else {
        state = muted[PLAYER_PARTS[i]] ? 1 : 0
      }
    }
    sendDiff(note, buttonLedMsg(note, state))
  }
  // Scene column: transport + grid octaves + metronome + mode.
  const playing = player.currentlyPlaying.value !== null && !player.isPaused.value
  const part = surfaceTargetPart()
  const noteGrid = gridMode.value === 'pads' && part !== 'drums'
  const base = gridBase(part)
  const scenes: (0 | 1 | 2)[] = [
    playing ? 2 : 1,                                             // 1 play/pause (blinks while playing)
    1,                                                           // 2 stop
    player.looping.value ? 1 : 0,                                // 3 loop
    stepSurface ? (stepSurface.recording() ? 2 : 1) : 0,         // 4 record (editor open)
    noteGrid && base < 127 - 42 ? 1 : 0,                         // 5 octave up
    noteGrid && base > 0 ? 1 : 0,                                // 6 octave down
    metro.enabled.value ? 1 : 0,                                 // 7 metronome
    stepSurface && gridMode.value === 'steps' ? 1 : 0,           // 8 grid mode
  ]
  scenes.forEach((state, i) => {
    const note = APC_SCENE_BTN_BASE + i
    sendDiff(note, buttonLedMsg(note, state))
  })
}

function renderFrame() {
  if (!output) return
  if (gridMode.value === 'steps' && stepSurface) renderStepsMode(stepSurface)
  else renderPadsMode()
  renderButtons()
}

// Metronome from the surface — same live/standalone split as TransportBar's
// toggle (the click rides a running transport, else runs its own).
function toggleMetronome(): void {
  const player = useMidiPlayer()
  const metro = useMetronome()
  const next = !metro.enabled.value
  metro.setEnabled(next)
  if (player.currentlyPlaying.value) {
    if (next) metro.startTicking(); else metro.stopTicking()
  } else {
    if (next) metro.startStandalone(); else metro.stopStandalone()
  }
}

// ── Input handling ───────────────────────────────────────────────────────────
function handleMessage(data: Uint8Array) {
  const player = useMidiPlayer()
  const ev = parseApcMessage(data)
  switch (ev.kind) {
    case 'pad': {
      if (gridMode.value === 'steps' && stepSurface) {
        if (!ev.on) return
        const step = page.value * APC_GRID_SIZE + ev.col
        if (ev.row < stepSurface.lanes().length && step < stepSurface.stepCount()) {
          stepSurface.toggleStep(ev.row, step)
          renderFrame()   // reflect the toggle immediately, not on the next tick
        }
        return
      }
      const part = surfaceTargetPart()
      const pitches = padPitches(ev.col, ev.row, part)
      const note = cellToPad(ev.col, ev.row)
      if (ev.on) {
        if (pitches === null) return
        heldPads.set(note, pitches)
        // The mk2 pads aren't velocity-sensitive (always 127) — send the pad
        // velocity set on fader 8 instead of max, so takes aren't all-accents.
        const vel = ev.velocity >= 127 ? padVelocity.value : ev.velocity / 127
        for (const p of pitches) dispatchSurfaceNote('on', p, vel)
      } else {
        // Release the pitches this pad actually started (the layout may have moved).
        const sounding = heldPads.get(note) ?? pitches ?? []
        heldPads.delete(note)
        for (const p of sounding) dispatchSurfaceNote('off', p, 0)
      }
      renderFrame()
      return
    }
    case 'track': {
      if (!ev.on) return
      if (gridMode.value === 'steps' && stepSurface) {
        if (ev.index < Math.ceil(stepSurface.stepCount() / APC_GRID_SIZE)) page.value = ev.index
      } else if (ev.index < PLAYER_PARTS.length) {
        // Shift layer: solo instead of mute (press again to unsolo).
        if (shiftHeld) player.soloPart(PLAYER_PARTS[ev.index])
        else player.toggleMute(PLAYER_PARTS[ev.index])
      }
      renderFrame()
      return
    }
    case 'shift': {
      shiftHeld = ev.on
      renderFrame()   // track row flips between mute view and solo view
      return
    }
    case 'scene': {
      if (!ev.on) return
      if (ev.index === 0) void player.playPause()
      else if (ev.index === 1) player.stop()
      else if (ev.index === 2) player.setLooping(!player.looping.value)
      else if (ev.index === 3) stepSurface?.toggleRecord()
      else if ((ev.index === 4 || ev.index === 5) && gridMode.value === 'pads' && surfaceTargetPart() !== 'drums') {
        // Octave up/down for the note/chord grid; kill held notes so none stick.
        const part = surfaceTargetPart()
        const next = octaveShift.value + (ev.index === 4 ? 1 : -1)
        if (gridBase(part) !== Math.max(0, Math.min(127 - 42, noteGridBaseFor(part) + next * 12))) {
          releaseHeld()
          octaveShift.value = next
        }
      }
      else if (ev.index === 6) toggleMetronome()
      else if (ev.index === 7 && stepSurface) {
        gridMode.value = gridMode.value === 'steps' ? 'pads' : 'steps'
      }
      renderFrame()
      return
    }
    case 'fader': {
      if (ev.index < PLAYER_PARTS.length) player.setPartLevel(PLAYER_PARTS[ev.index], ev.value)
      else if (ev.index === 7) padVelocity.value = Math.max(0.05, ev.value)   // pad velocity (floor: never silent)
      else if (ev.index === 8) player.setVolume(Math.round(ev.value * 100))
      return
    }
    default:
      return
  }
}

// ── Driver registration (surface slot in useMidiInput) ───────────────────────
function attach(input: WebMidiInput, out: WebMidiOutput): () => void {
  output = out
  lastFrame.clear()
  heldPads.clear()
  shiftHeld = false
  for (const m of blackoutMsgs()) out.send(m)      // never inherit stale LEDs
  input.onmidimessage = (e) => handleMessage(e.data)
  connected.value = true
  renderFrame()
  // Poll-render: one loop covers every state source (mutes, transport, playhead)
  // and the diff keeps the wire quiet when nothing changed.
  refreshTimer = setInterval(renderFrame, 66)
  return () => {
    if (refreshTimer !== null) { clearInterval(refreshTimer); refreshTimer = null }
    input.onmidimessage = null
    releaseHeld()   // no pitch keeps ringing after the surface lets go
    try { for (const m of blackoutMsgs()) out.send(m) } catch { /* port may be gone */ }
    output = null
    connected.value = false
  }
}

let registered = false
/** Install the APC mini mk2 driver into useMidiInput's surface slot (idempotent). */
export function registerApcMiniDriver(): void {
  if (registered) return
  registered = true
  registerSurfaceDriver({
    pickPorts: (inputs, outputs) => {
      mk1Detected.value = inputs.some(i => isApcMiniMk1(i.name))
      const input = pickApcPort(inputs)
      const out = pickApcPort(outputs)
      return input && out ? { input, output: out } : null
    },
    attach,
  })
}

export function useApcMini() {
  return { connected, mk1Detected, gridMode, page, octaveShift, padVelocity }
}
