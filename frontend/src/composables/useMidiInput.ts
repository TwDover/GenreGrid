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
import { useMidiPlayer, type PlayerPart } from './useMidiPlayer'
import { activeStyleId } from './useStyleCatalog'
import { isDrumPitch } from '../utils/pianoRollEdit'

// ── Pure MIDI message parsing (unit-tested) ──────────────────────────────────
export interface MidiNoteEvent { type: 'noteon' | 'noteoff' | 'other'; note: number; velocity: number }

/** Decode a raw MIDI message [status, data1, data2] into a note event. A note-on
 *  with zero velocity is the running-status convention for a note-off, so it's
 *  normalized here; the channel nibble is ignored (audition is channel-agnostic). */
export function parseMidiMessage(data: ArrayLike<number>): MidiNoteEvent {
  const cmd = (data[0] ?? 0) & 0xf0
  const note = data[1] ?? 0
  const velocity = data[2] ?? 0
  if (cmd === 0x90 && velocity > 0) return { type: 'noteon', note, velocity }
  if (cmd === 0x80 || (cmd === 0x90 && velocity === 0)) return { type: 'noteoff', note, velocity: 0 }
  return { type: 'other', note, velocity }
}

// Minimal Web MIDI surface — declared locally so the composable doesn't depend on
// the lib.dom WebMIDI types being present in this TS config.
export type WebMidiInput = { id: string; name: string | null; onmidimessage: ((e: { data: Uint8Array }) => void) | null }
export type WebMidiOutput = { id: string; name: string | null; send: (data: number[]) => void }
type WebMidiAccess = {
  inputs: Map<string, WebMidiInput>
  outputs?: Map<string, WebMidiOutput>
  onstatechange: ((e: unknown) => void) | null
}

// Note-event tap: consumers (e.g. the recorder) subscribe to the live note stream
// that also drives audition. `velocity` is 0..1; note-off carries velocity 0.
export interface LiveNote { type: 'on' | 'off'; note: number; velocity: number }
const noteListeners = new Set<(ev: LiveNote) => void>()
/** Subscribe to live MIDI note-on/off (already parsed + filtered). Returns an unsubscribe. */
export function onMidiNote(cb: (ev: LiveNote) => void): () => void {
  noteListeners.add(cb)
  return () => { noteListeners.delete(cb) }
}

// ── Shared module state (one MIDI-in session across the app) ─────────────────
const enabled = ref(false)
const requesting = ref(false)
const error = ref<string | null>(null)
const devices = ref<{ id: string; name: string }[]>([])
const selectedId = ref<string | null>(null)   // null = listen to all inputs
const part = ref<PlayerPart>('melody')         // which voice the controller plays
const activeNotes = ref(0)                      // held-note count (drives a UI pulse)

let access: WebMidiAccess | null = null

// Audition override: while a consumer (e.g. the piano-roll editor) is open, monitor
// through THAT part's exact voice+style instead of the global "now playing" one.
// Key/scale ride along when the consumer knows them (the editor does) so control
// surfaces can light in-key pads and build diatonic chords.
let auditionOverride: {
  style: string | undefined; part: PlayerPart; keyRoot?: string; scale?: string
} | null = null
/** Route MIDI-in monitoring through a specific style+part (the thing being edited). */
export function setAuditionTarget(style: string | undefined, part: PlayerPart,
  keyRoot?: string, scale?: string): void {
  auditionOverride = { style, part, keyRoot, scale }
}
export function clearAuditionTarget(): void { auditionOverride = null }

/** Key/scale of the audition target, when the consumer provided them (else null). */
export function surfaceKeyScale(): { keyRoot: string; scale: string } | null {
  return auditionOverride?.keyRoot && auditionOverride?.scale
    ? { keyRoot: auditionOverride.keyRoot, scale: auditionOverride.scale }
    : null
}

// Where each sounding note was routed at note-ON, keyed by pitch. The off must
// release the SAME voice — resolving routing again at note-off sends the release
// to the wrong instrument when the target changed mid-note (e.g. an editor
// closing under a held key), leaving the old voice ringing forever.
const soundingRoutes = new Map<number, { style: string | undefined; part: PlayerPart }>()

// ── Control-surface driver (e.g. the APC mini) ───────────────────────────────
// A driver claims a matched input+output port pair for itself: its input bypasses
// the generic note path (grid pads aren't piano keys) and its output drives LEDs.
// One driver slot is enough — we only ship one surface.
export interface SurfaceDriver {
  /** Pick the port pair this surface owns from the live port lists (null = absent). */
  pickPorts: (inputs: WebMidiInput[], outputs: WebMidiOutput[]) =>
    { input: WebMidiInput; output: WebMidiOutput } | null
  /** Wire up the surface; returns a detach that must clear LEDs + handlers. */
  attach: (input: WebMidiInput, output: WebMidiOutput) => () => void
}
let surfaceDriver: SurfaceDriver | null = null
let surfaceDetach: (() => void) | null = null
let surfaceInputId: string | null = null
// Set by every useMidiInput() call (all instances act on the same module state);
// lets a late registerSurfaceDriver() attach to an already-enabled session.
let _rebindPorts: (() => void) | null = null

/** Register the app's control-surface driver (call once at startup). */
export function registerSurfaceDriver(d: SurfaceDriver): void {
  surfaceDriver = d
  _rebindPorts?.()
}

/** The part a control surface is currently playing: the open editor's part when
 *  one is live (the audition override), else the configured default voice. The
 *  driver polls this to pick its grid layout (drum rack vs melodic note grid). */
export function surfaceTargetPart(): PlayerPart {
  return auditionOverride ? auditionOverride.part : part.value
}

/** Inject a note from a control surface (the driver remaps pads → pitches and
 *  feeds them here). Routed exactly like a regular controller note: style/part
 *  follow the audition override, then the default voice — so pads play whatever
 *  instrument is selected, and recorders hear them too. velocity is 0..1. */
export function dispatchSurfaceNote(type: 'on' | 'off', note: number, velocity: number): void {
  const player = useMidiPlayer()
  const style = auditionOverride ? auditionOverride.style : (activeStyleId.value ?? undefined)
  const prt = surfaceTargetPart()
  if (type === 'on') {
    if (prt === 'drums' && !isDrumPitch(note)) return   // same guard as the generic path
    soundingRoutes.set(note, { style, part: prt })
    activeNotes.value++
    player.auditionOn(style, prt, note, velocity)
    noteListeners.forEach(l => l({ type: 'on', note, velocity }))
  } else {
    // Release through the note-ON's routing (see soundingRoutes above).
    const route = soundingRoutes.get(note) ?? { style, part: prt }
    soundingRoutes.delete(note)
    if (route.part === 'drums' && !isDrumPitch(note)) return
    activeNotes.value = Math.max(0, activeNotes.value - 1)
    player.auditionOff(route.style, route.part, note)
    noteListeners.forEach(l => l({ type: 'off', note, velocity: 0 }))
  }
}

export function useMidiInput() {
  const player = useMidiPlayer()
  const supported = typeof navigator !== 'undefined' && 'requestMIDIAccess' in navigator

  function refreshDevices() {
    // The claimed surface port isn't a generic input — keep it out of the picker.
    devices.value = access
      ? [...access.inputs.values()].filter(i => i.id !== surfaceInputId)
          .map(i => ({ id: i.id, name: i.name || 'MIDI input' }))
      : []
    if (selectedId.value && !devices.value.some(d => d.id === selectedId.value)) selectedId.value = null
  }

  // (Re)attach the registered surface driver to its port pair, if present. Called
  // before bindInputs so the generic path skips the claimed input.
  function bindSurface() {
    if (!access || !surfaceDriver) return
    const picked = surfaceDriver.pickPorts([...access.inputs.values()], [...(access.outputs?.values() ?? [])])
    if (surfaceDetach && (!picked || picked.input.id !== surfaceInputId)) {
      surfaceDetach(); surfaceDetach = null; surfaceInputId = null   // unplugged or moved
    }
    if (picked && !surfaceDetach) {
      surfaceInputId = picked.input.id
      surfaceDetach = surfaceDriver.attach(picked.input, picked.output)
    }
  }
  function unbindSurface() {
    surfaceDetach?.(); surfaceDetach = null; surfaceInputId = null
  }

  function handleMessage(input: WebMidiInput, data: Uint8Array) {
    if (selectedId.value && input.id !== selectedId.value) return   // honor the device filter
    const ev = parseMidiMessage(data)
    // Same routing as surface notes: override wins, drums range-filters (a keyboard
    // played as drums sends chromatic notes that map to no kit piece), and the
    // note-off releases whatever voice its note-on started.
    if (ev.type === 'noteon') dispatchSurfaceNote('on', ev.note, ev.velocity / 127)
    else if (ev.type === 'noteoff') dispatchSurfaceNote('off', ev.note, 0)
  }

  function bindInputs() {
    if (!access) return
    for (const input of access.inputs.values()) {
      if (input.id === surfaceInputId) continue   // the surface driver owns this port
      input.onmidimessage = (e) => handleMessage(input, e.data)
    }
  }
  function unbindInputs() {
    if (!access) return
    for (const input of access.inputs.values()) {
      if (input.id === surfaceInputId) continue
      input.onmidimessage = null
    }
  }

  _rebindPorts = () => { if (enabled.value) { bindSurface(); bindInputs(); refreshDevices() } }

  async function enable() {
    if (enabled.value || requesting.value) return
    if (!supported) { error.value = 'Web MIDI is not available in this build.'; return }
    requesting.value = true
    error.value = null
    try {
      const req = (navigator as unknown as { requestMIDIAccess: (o?: { sysex?: boolean }) => Promise<WebMidiAccess> }).requestMIDIAccess
      access = await req.call(navigator, { sysex: false })
      // Hot-plug: rebind + refresh whenever a device connects/disconnects.
      // Surface first, so the generic binding skips the port the driver claimed.
      access.onstatechange = () => { if (enabled.value) { bindSurface(); bindInputs() } refreshDevices() }
      bindSurface()
      refreshDevices()
      bindInputs()
      enabled.value = true
      // Remember across sessions so a connected surface lights up on next launch.
      try { localStorage.setItem('genregrid_midi_on', '1') } catch { /* storage unavailable */ }
      player.prepareAudition(activeStyleId.value ?? undefined, part.value, true)   // warm the (sustaining) voice
    } catch (e) {
      error.value = (e as Error)?.message || 'MIDI access was denied.'
      access = null
    } finally {
      requesting.value = false
    }
  }

  function disable() {
    unbindSurface()   // driver detach clears the LEDs before we let go of the port
    unbindInputs()
    if (access) access.onstatechange = null
    enabled.value = false
    activeNotes.value = 0
    try { localStorage.removeItem('genregrid_midi_on') } catch { /* storage unavailable */ }
  }

  /** True when the last session left MIDI input on (drives startup auto-enable). */
  function wasEnabledLastSession(): boolean {
    try { return localStorage.getItem('genregrid_midi_on') === '1' } catch { return false }
  }

  function toggle() { return enabled.value ? disable() : enable() }

  /** Switch which part's voice the controller plays; re-warm it if we're live. */
  function setPart(p: PlayerPart) {
    part.value = p
    if (enabled.value) player.prepareAudition(activeStyleId.value ?? undefined, p, true)
  }

  return { supported, enabled, requesting, error, devices, selectedId, part, activeNotes, enable, disable, toggle, setPart, wasEnabledLastSession }
}
