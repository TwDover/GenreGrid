<!--
  GenreGrid — a style-based MIDI generator.
  Copyright (C) 2026 Tw Dover

  This program is free software: you can redistribute it and/or modify it under
  the terms of the GNU General Public License v3 or (at your option) any later
  version. Distributed WITHOUT ANY WARRANTY. See <https://www.gnu.org/licenses/>.
-->
<!--
  Live MIDI input configuration, lifted out of the transport play bar so MIDI is a
  shared, always-configurable resource: anything that needs it (the piano-roll editor
  auditions/records through it) takes control contextually. Here you enable input,
  pick a device, and set the default voice a controller plays when no editor is open.
-->
<template>
  <section class="midi-settings">
    <div class="ms-head">
      <span class="ms-title">MIDI Input</span>
      <span
        v-if="enabled && activeNotes > 0"
        class="ms-dot"
        title="Receiving notes"
      ></span>
    </div>

    <p v-if="!supported" class="ms-note">Web MIDI isn't available in this build.</p>

    <template v-else>
      <div class="ms-row">
        <button
          class="ms-toggle"
          :class="{ 'is-on': enabled }"
          :disabled="requesting"
          :aria-pressed="enabled"
          @click="toggle"
        >{{ requesting ? 'Enabling…' : enabled ? 'On' : 'Off' }}</button>
        <span class="ms-desc">Play a connected controller through GenreGrid's voices. Opening a stem's editor routes it to that instrument automatically.</span>
      </div>

      <template v-if="enabled">
        <label class="ms-field">
          <span class="ms-label">Default voice</span>
          <select :value="part" @change="onPart" title="Which voice a controller plays when no editor is open">
            <option v-for="p in MIDI_PARTS" :key="p" :value="p">{{ p.replace('_', ' ') }}</option>
          </select>
        </label>

        <label class="ms-field">
          <span class="ms-label">Device</span>
          <select v-if="devices.length" :value="selectedId ?? ''" @change="onDevice" title="MIDI input device">
            <option value="">All inputs</option>
            <option v-for="d in devices" :key="d.id" :value="d.id">{{ d.name }}</option>
          </select>
          <span v-else class="ms-hint">No device connected</span>
        </label>
      </template>

      <div v-if="enabled" class="ms-apc">
        <div class="ms-apc-row">
          <span class="ms-label">APC mini mk2</span>
          <span class="ms-apc-status" :class="{ 'is-live': apc.connected.value }">
            {{ apc.connected.value ? 'Connected — lights on' : 'Not detected' }}
          </span>
        </div>
        <p v-if="apc.mk1Detected.value && !apc.connected.value" class="ms-hint">
          An original APC mini was found — the light show needs the mk2.
        </p>
        <details v-if="apc.connected.value" class="ms-apc-map">
          <summary>Control mapping</summary>
          <ul>
            <li><b>Pads</b> — play &amp; record the selected voice: drums = a 4×4 drum rack (bottom-left, lit by piece); chords = a chord grid (columns = scale degrees, one pad = one triad); other voices = a note grid in fourths. With a stem's editor open, the grid lights in that stem's key (roots cyan, in-scale dim, out-of-key dark)</li>
            <li><b>Grid (drum editor open)</b> — scene button 8 switches to a step sequencer: rows = kit lanes, columns = 1/16 steps, track buttons page</li>
            <li><b>Scene buttons</b> — 1 play/pause · 2 stop · 3 loop · 4 record · 5/6 octave up/down · 7 metronome</li>
            <li><b>Track buttons</b> — mute parts 1–7 (drums, bass, chords, melody, arp, pads, counter); hold <b>Shift</b> for solo</li>
            <li><b>Faders</b> — 1–7 part levels · 8 pad velocity · 9 master volume</li>
          </ul>
        </details>
      </div>

      <p v-if="error" class="ms-error">{{ error }}</p>
    </template>
  </section>
</template>

<script setup lang="ts">
import { useMidiInput } from '../composables/useMidiInput'
import { useApcMini } from '../composables/useApcMini'
import type { PlayerPart } from '../composables/useMidiPlayer'

const {
  supported, enabled, requesting, error, devices, selectedId, part, activeNotes,
  toggle, setPart,
} = useMidiInput()
const apc = useApcMini()

const MIDI_PARTS = ['melody', 'chords', 'bass', 'pads', 'arpeggio', 'counter_melody', 'drums'] as const
function onPart(e: Event) { setPart((e.target as HTMLSelectElement).value as PlayerPart) }
function onDevice(e: Event) { selectedId.value = (e.target as HTMLSelectElement).value || null }
</script>

<style scoped>
.midi-settings {
  display: flex; flex-direction: column; gap: var(--s3);
  padding-bottom: var(--s5); margin-bottom: var(--s5);
  border-bottom: 1px solid var(--line);
}
.ms-head { display: flex; align-items: center; gap: var(--s2); }
.ms-title { font-size: var(--t-body); font-weight: 600; color: var(--ink); }
.ms-dot {
  width: 8px; height: 8px; border-radius: 50%; background: var(--accent);
  box-shadow: 0 0 6px var(--accent); animation: ms-pulse 0.6s ease-out infinite;
}
@keyframes ms-pulse { 0% { transform: scale(0.7); opacity: 0.6; } 100% { transform: scale(1.3); opacity: 1; } }

.ms-note { font-size: var(--t-meta); color: var(--ink-faint); margin: 0; }

.ms-row { display: flex; align-items: center; gap: var(--s3); }
.ms-toggle {
  flex-shrink: 0; min-width: 56px; height: 30px;
  border: 1px solid var(--line); border-radius: var(--r-sm);
  background: var(--surface); color: var(--ink-dim);
  font-size: var(--t-meta); font-weight: 600; cursor: pointer;
  transition: background .14s, color .14s, border-color .14s;
}
.ms-toggle:hover:not(:disabled) { color: var(--ink); border-color: var(--ink-faint); }
.ms-toggle:disabled { opacity: 0.6; cursor: default; }
.ms-toggle.is-on { background: var(--accent-wash); border-color: var(--accent-edge); color: var(--accent); }
.ms-desc { font-size: var(--t-meta); color: var(--ink-dim); line-height: 1.4; }

.ms-field { display: flex; align-items: center; gap: var(--s3); }
.ms-label { width: 96px; flex-shrink: 0; font-size: var(--t-meta); color: var(--ink-dim); }
.ms-field select {
  flex: 1; min-width: 0; height: 30px; text-transform: capitalize;
  background: var(--surface); color: var(--ink); border: 1px solid var(--line);
  border-radius: var(--r-sm); padding: 0 var(--s2);
}
.ms-hint { flex: 1; font-size: var(--t-meta); color: var(--ink-faint); font-style: italic; }
.ms-error { font-size: var(--t-meta); color: var(--bad); margin: 0; }

.ms-apc { display: flex; flex-direction: column; gap: var(--s2); }
.ms-apc-row { display: flex; align-items: center; gap: var(--s3); }
.ms-apc-status { font-size: var(--t-meta); color: var(--ink-faint); }
.ms-apc-status.is-live { color: var(--accent); }
.ms-apc-map { font-size: var(--t-meta); color: var(--ink-dim); }
.ms-apc-map summary { cursor: pointer; color: var(--ink-faint); }
.ms-apc-map ul { margin: var(--s2) 0 0; padding-left: var(--s5); display: flex; flex-direction: column; gap: 2px; }
.ms-apc-map b { color: var(--ink-dim); font-weight: 600; }
</style>
