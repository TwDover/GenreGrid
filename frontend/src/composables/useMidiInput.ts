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
type WebMidiInput = { id: string; name: string | null; onmidimessage: ((e: { data: Uint8Array }) => void) | null }
type WebMidiAccess = { inputs: Map<string, WebMidiInput>; onstatechange: ((e: unknown) => void) | null }

// ── Shared module state (one MIDI-in session across the app) ─────────────────
const enabled = ref(false)
const requesting = ref(false)
const error = ref<string | null>(null)
const devices = ref<{ id: string; name: string }[]>([])
const selectedId = ref<string | null>(null)   // null = listen to all inputs
const part = ref<PlayerPart>('melody')         // which voice the controller plays
const activeNotes = ref(0)                      // held-note count (drives a UI pulse)

let access: WebMidiAccess | null = null

export function useMidiInput() {
  const player = useMidiPlayer()
  const supported = typeof navigator !== 'undefined' && 'requestMIDIAccess' in navigator

  function refreshDevices() {
    devices.value = access ? [...access.inputs.values()].map(i => ({ id: i.id, name: i.name || 'MIDI input' })) : []
    if (selectedId.value && !devices.value.some(d => d.id === selectedId.value)) selectedId.value = null
  }

  function handleMessage(input: WebMidiInput, data: Uint8Array) {
    if (selectedId.value && input.id !== selectedId.value) return   // honor the device filter
    const ev = parseMidiMessage(data)
    const style = activeStyleId.value ?? undefined
    if (ev.type === 'noteon') {
      activeNotes.value++
      player.auditionOn(style, part.value, ev.note, ev.velocity / 127)
    } else if (ev.type === 'noteoff') {
      activeNotes.value = Math.max(0, activeNotes.value - 1)
      player.auditionOff(style, part.value, ev.note)
    }
  }

  function bindInputs() {
    if (!access) return
    for (const input of access.inputs.values()) input.onmidimessage = (e) => handleMessage(input, e.data)
  }
  function unbindInputs() {
    if (!access) return
    for (const input of access.inputs.values()) input.onmidimessage = null
  }

  async function enable() {
    if (enabled.value || requesting.value) return
    if (!supported) { error.value = 'Web MIDI is not available in this build.'; return }
    requesting.value = true
    error.value = null
    try {
      const req = (navigator as unknown as { requestMIDIAccess: (o?: { sysex?: boolean }) => Promise<WebMidiAccess> }).requestMIDIAccess
      access = await req.call(navigator, { sysex: false })
      // Hot-plug: rebind + refresh whenever a device connects/disconnects.
      access.onstatechange = () => { refreshDevices(); if (enabled.value) bindInputs() }
      refreshDevices()
      bindInputs()
      enabled.value = true
      player.prepareAudition(activeStyleId.value ?? undefined, part.value, true)   // warm the (sustaining) voice
    } catch (e) {
      error.value = (e as Error)?.message || 'MIDI access was denied.'
      access = null
    } finally {
      requesting.value = false
    }
  }

  function disable() {
    unbindInputs()
    if (access) access.onstatechange = null
    enabled.value = false
    activeNotes.value = 0
  }

  function toggle() { return enabled.value ? disable() : enable() }

  /** Switch which part's voice the controller plays; re-warm it if we're live. */
  function setPart(p: PlayerPart) {
    part.value = p
    if (enabled.value) player.prepareAudition(activeStyleId.value ?? undefined, p, true)
  }

  return { supported, enabled, requesting, error, devices, selectedId, part, activeNotes, enable, disable, toggle, setPart }
}
