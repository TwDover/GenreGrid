<!--
  GenreGrid — a style-based MIDI generator.
  Copyright (C) 2026 Tw Dover

  This program is free software: you can redistribute it and/or modify it under
  the terms of the GNU General Public License as published by the Free Software
  Foundation, either version 3 of the License, or (at your option) any later
  version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
  <https://www.gnu.org/licenses/> for details.
-->
<!--
  Synth designer (roadmap 6.6) — shape a subtractive voice from oscillator + amp
  envelope and audition it on a keyboard. First designer slice: oscillator and amp
  ADSR are editable here; filter / LFO / FX arrive in later slices, but a chosen
  preset's filter and FX still SOUND (buildSynthFromPatch renders the whole patch),
  so presets audition faithfully today. Nothing is assigned to a part yet — this is a
  sound-design sandbox until the routing slice lands.
-->
<template>
  <div v-if="open" class="sd-overlay" @click.self="close" @keydown.esc="close">
    <div class="sd-modal" role="dialog" aria-label="Synth designer">
      <header class="sd-header">
        <h2>Synth Designer</h2>
        <button class="sd-x" title="Close" @click="close">✕</button>
      </header>

      <!-- ── Preset ─────────────────────────────────────────────────────────── -->
      <section class="sd-first">
        <div class="sd-head-row">
          <h3>Preset</h3>
          <select v-model="selectedPreset" class="sd-input sd-preset" @change="loadPreset(selectedPreset)">
            <option v-for="p in PRESETS" :key="p.id" :value="p.id">{{ p.label }}</option>
          </select>
        </div>
        <p class="sd-hint">
          The seven built-in voices, as editable patches. Editing oscillator or envelope marks the
          patch as modified; the preset menu reloads it. Filter, modulation and FX controls are
          coming — a preset's filter/FX still play.
        </p>
      </section>

      <!-- ── Oscillator ─────────────────────────────────────────────────────── -->
      <section>
        <h3>Oscillator</h3>
        <div class="sd-row">
          <span class="sd-label">Wave</span>
          <select class="sd-input" :value="patch.oscillator.type" @change="setWave(($event.target as HTMLSelectElement).value as OscillatorWave)">
            <option v-for="w in WAVES" :key="w" :value="w">{{ w }}</option>
          </select>
        </div>
        <template v-if="isFat">
          <div class="sd-row">
            <span class="sd-label">Unison</span>
            <input v-model.number="patch.oscillator.count" class="sd-slider" type="range" min="1" max="7" step="1" />
            <span class="sd-val">{{ patch.oscillator.count }} voices</span>
          </div>
          <div class="sd-row">
            <span class="sd-label">Spread</span>
            <input v-model.number="patch.oscillator.spread" class="sd-slider" type="range" min="0" max="100" step="1" />
            <span class="sd-val">{{ patch.oscillator.spread }} ¢</span>
          </div>
        </template>
      </section>

      <!-- ── Amp envelope ───────────────────────────────────────────────────── -->
      <section>
        <h3>Amp Envelope</h3>
        <div class="sd-row">
          <span class="sd-label">Attack</span>
          <input v-model.number="patch.ampEnvelope.attack" class="sd-slider" type="range" min="0.001" max="2" step="0.001" />
          <span class="sd-val">{{ secs(patch.ampEnvelope.attack) }}</span>
        </div>
        <div class="sd-row">
          <span class="sd-label">Decay</span>
          <input v-model.number="patch.ampEnvelope.decay" class="sd-slider" type="range" min="0.001" max="2" step="0.001" />
          <span class="sd-val">{{ secs(patch.ampEnvelope.decay) }}</span>
        </div>
        <div class="sd-row">
          <span class="sd-label">Sustain</span>
          <input v-model.number="patch.ampEnvelope.sustain" class="sd-slider" type="range" min="0" max="1" step="0.01" />
          <span class="sd-val">{{ patch.ampEnvelope.sustain.toFixed(2) }}</span>
        </div>
        <div class="sd-row">
          <span class="sd-label">Release</span>
          <input v-model.number="patch.ampEnvelope.release" class="sd-slider" type="range" min="0.001" max="4" step="0.001" />
          <span class="sd-val">{{ secs(patch.ampEnvelope.release) }}</span>
        </div>
        <div class="sd-row">
          <span class="sd-label">Level</span>
          <input v-model.number="patch.ampEnvelope.level" class="sd-slider" type="range" min="-30" max="0" step="0.5" />
          <span class="sd-val">{{ patch.ampEnvelope.level }} dB</span>
        </div>
      </section>

      <!-- ── Keyboard ───────────────────────────────────────────────────────── -->
      <section>
        <h3>Audition</h3>
        <div class="sd-kbd">
          <button
            v-for="k in whiteKeys"
            :key="k.note"
            class="sd-key sd-white"
            :title="k.note"
            @mousedown="play(k.note)"
          >{{ k.note }}</button>
          <button
            v-for="k in blackKeys"
            :key="k.note"
            class="sd-key sd-black"
            :style="{ left: `${(k.pos / totalWhite) * 100}%` }"
            :title="k.note"
            @mousedown.stop="play(k.note)"
          ></button>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue'
import { useSynthDesigner } from '../composables/useSynthDesigner'
import { auditionPatchNote, disposeSynthPreview } from '../soundfonts/audition'
import {
  type SynthPatch, type OscillatorWave,
  PRESET_MELODY_LEAD_SOFT, PRESET_SYNTH_LEAD, PRESET_SYNTH_CHORDS, PRESET_ARP_PLUCK,
  PRESET_PAD, PRESET_STRINGS, PRESET_SYNTH_BASS, PRESET_LOFI,
} from '../soundfonts/synthPatch'

const { open, close } = useSynthDesigner()

const PRESETS: { id: string; label: string; patch: SynthPatch }[] = [
  { id: 'melody_lead_soft', label: 'Melody Lead (soft)', patch: PRESET_MELODY_LEAD_SOFT },
  { id: 'synth_lead', label: 'Synth Lead', patch: PRESET_SYNTH_LEAD },
  { id: 'synth_chords', label: 'Synth Chords', patch: PRESET_SYNTH_CHORDS },
  { id: 'arp_pluck', label: 'Arp Pluck', patch: PRESET_ARP_PLUCK },
  { id: 'pad', label: 'Pad', patch: PRESET_PAD },
  { id: 'strings', label: 'Strings', patch: PRESET_STRINGS },
  { id: 'synth_bass', label: 'Synth Bass', patch: PRESET_SYNTH_BASS },
  { id: 'lofi', label: 'Lo-fi', patch: PRESET_LOFI },
]

const WAVES: OscillatorWave[] = ['sine', 'triangle', 'sawtooth', 'square', 'pulse', 'fatsine', 'fattriangle', 'fatsawtooth', 'fatsquare']

const clone = (p: SynthPatch): SynthPatch => JSON.parse(JSON.stringify(p))

const selectedPreset = ref(PRESETS[0].id)
const patch = ref<SynthPatch>(clone(PRESETS[0].patch))

function loadPreset(id: string) {
  const found = PRESETS.find(p => p.id === id)
  if (found) patch.value = clone(found.patch)
}

const isFat = computed(() => patch.value.oscillator.type.startsWith('fat'))

// Switching wave families keeps the options valid: fat waves need unison count/spread;
// plain waves must not carry them, or the oscillator options wouldn't match a plain
// voice (patchToNodeSpec passes count/spread through whenever they're present).
function setWave(w: OscillatorWave) {
  patch.value.oscillator.type = w
  if (w.startsWith('fat')) {
    if (patch.value.oscillator.count === undefined) patch.value.oscillator.count = 3
    if (patch.value.oscillator.spread === undefined) patch.value.oscillator.spread = 20
  } else {
    delete patch.value.oscillator.count
    delete patch.value.oscillator.spread
  }
}

const secs = (s: number) => (s >= 1 ? `${s.toFixed(2)} s` : `${Math.round(s * 1000)} ms`)

function play(note: string) {
  void auditionPatchNote(patch.value, note)
}

// ── Keyboard layout: two octaves, black keys placed over the white-key row ────
const OCTAVES = [3, 4]
const WHITE_NAMES = ['C', 'D', 'E', 'F', 'G', 'A', 'B']
const BLACK_DEFS = [{ name: 'C#', pos: 1 }, { name: 'D#', pos: 2 }, { name: 'F#', pos: 4 }, { name: 'G#', pos: 5 }, { name: 'A#', pos: 6 }]
const totalWhite = OCTAVES.length * WHITE_NAMES.length
const whiteKeys = OCTAVES.flatMap(o => WHITE_NAMES.map(n => ({ note: `${n}${o}` })))
const blackKeys = OCTAVES.flatMap((o, oi) => BLACK_DEFS.map(b => ({ note: `${b.name}${o}`, pos: oi * WHITE_NAMES.length + b.pos })))

watch(open, (v) => { if (!v) disposeSynthPreview() })
onUnmounted(disposeSynthPreview)
</script>

<style scoped>
.sd-overlay {
  position: fixed; inset: 0; z-index: 1000;
  background: rgba(0, 0, 0, 0.5);
  display: flex; align-items: center; justify-content: center; padding: 1rem;
}
.sd-modal {
  background: var(--surface); color: var(--text);
  border: 1px solid var(--border); border-radius: 10px;
  width: min(560px, 100%); max-height: 86vh; overflow: auto;
  padding: 1rem 1.25rem;
}
.sd-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.5rem; }
.sd-header h2 { margin: 0; font-size: 1.1rem; }
.sd-x { background: none; border: none; color: var(--text-faint); cursor: pointer; font-size: 1rem; }
.sd-x:hover { color: var(--text); }
section { border-top: 1px solid var(--border); padding-top: 0.85rem; margin-top: 0.85rem; }
.sd-first { border-top: none; padding-top: 0; margin-top: 0; }
h3 { font-size: 0.85rem; margin: 0 0 0.5rem; color: var(--text); }
.sd-hint { font-size: 0.78rem; color: var(--text-faint); margin: 0.5rem 0 0; line-height: 1.5; }
.sd-input {
  font: inherit; padding: 0.35rem 0.5rem; border: 1px solid var(--border);
  border-radius: 6px; background: var(--surface); color: var(--text);
}
.sd-head-row { display: flex; align-items: center; justify-content: space-between; gap: 0.6rem; }
.sd-preset { min-width: 200px; }
.sd-row { display: grid; grid-template-columns: 68px 1fr 84px; align-items: center; gap: 0.6rem; margin-bottom: 0.45rem; }
.sd-label { font-size: 0.8rem; color: var(--text-faint); }
.sd-slider { width: 100%; accent-color: var(--accent); }
.sd-val { font-size: 0.76rem; color: var(--text-faint); text-align: right; font-variant-numeric: tabular-nums; }

/* Keyboard: white keys in a flex row, black keys absolutely positioned over it. */
.sd-kbd { position: relative; display: flex; height: 128px; user-select: none; margin-top: 0.25rem; }
.sd-key { cursor: pointer; padding: 0; font: inherit; }
.sd-white {
  flex: 1; background: var(--surface); color: var(--text-faint);
  border: 1px solid var(--border); border-radius: 0 0 4px 4px;
  display: flex; align-items: flex-end; justify-content: center;
  font-size: 0.6rem; padding-bottom: 0.3rem;
}
.sd-white:first-child { border-top-left-radius: 4px; }
.sd-white:last-child { border-top-right-radius: 4px; }
.sd-white:active { background: var(--accent); color: var(--accent-contrast, #fff); }
.sd-black {
  position: absolute; top: 0; transform: translateX(-50%);
  width: calc(100% / 14 * 0.62); height: 62%;
  background: var(--text); border: 1px solid var(--border);
  border-radius: 0 0 3px 3px; z-index: 2;
}
.sd-black:active { background: var(--accent); }
</style>
