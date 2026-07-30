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
          The seven built-in voices, as editable patches — shape the oscillator, filter, envelopes,
          an LFO and the FX chain, and audition on the keyboard. Editing a control marks the patch
          as modified; the preset menu reloads it.
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

      <!-- ── Filter ─────────────────────────────────────────────────────────── -->
      <section>
        <div class="sd-head-row">
          <h3>Filter</h3>
          <label v-if="!isMono" class="sd-toggle">
            <input type="checkbox" :checked="hasFilter" @change="toggleFilter(($event.target as HTMLInputElement).checked)" />
            {{ hasFilter ? 'On' : 'Off' }}
          </label>
        </div>
        <template v-if="patch.filter">
          <div class="sd-row">
            <span class="sd-label">Type</span>
            <select class="sd-input" :value="patch.filter.type" @change="setFilterType(($event.target as HTMLSelectElement).value)">
              <option value="lowpass">lowpass</option>
              <option value="highpass">highpass</option>
              <option value="bandpass">bandpass</option>
            </select>
          </div>
          <div v-if="!isMono" class="sd-row">
            <span class="sd-label">Cutoff</span>
            <input v-model.number="cutoffPos" class="sd-slider" type="range" min="0" max="1000" step="1" />
            <span class="sd-val">{{ patch.filter.frequency }} Hz</span>
          </div>
          <p v-else class="sd-hint">Cutoff follows the filter envelope below.</p>
          <div class="sd-row">
            <span class="sd-label">Resonance</span>
            <input v-model.number="patch.filter.Q" class="sd-slider" type="range" min="0.1" max="20" step="0.1" />
            <span class="sd-val">Q {{ patch.filter.Q.toFixed(1) }}</span>
          </div>
          <div class="sd-row">
            <span class="sd-label">Rolloff</span>
            <select class="sd-input" :value="String(patch.filter.rolloff)" @change="setRolloff(($event.target as HTMLSelectElement).value)">
              <option value="-12">-12 dB/oct</option>
              <option value="-24">-24 dB/oct</option>
              <option value="-48">-48 dB/oct</option>
              <option value="-96">-96 dB/oct</option>
            </select>
          </div>
        </template>
        <p v-else class="sd-hint">No filter — the raw oscillator runs straight into the amp.</p>
      </section>

      <!-- ── Filter envelope (mono voices) ──────────────────────────────────── -->
      <section v-if="patch.filterEnvelope">
        <h3>Filter Envelope</h3>
        <p class="sd-hint">Sweeps the cutoff up from the base by the envelope depth — what makes the bass move.</p>
        <div class="sd-row">
          <span class="sd-label">Attack</span>
          <input v-model.number="patch.filterEnvelope.attack" class="sd-slider" type="range" min="0.001" max="2" step="0.001" />
          <span class="sd-val">{{ secs(patch.filterEnvelope.attack) }}</span>
        </div>
        <div class="sd-row">
          <span class="sd-label">Decay</span>
          <input v-model.number="patch.filterEnvelope.decay" class="sd-slider" type="range" min="0.001" max="2" step="0.001" />
          <span class="sd-val">{{ secs(patch.filterEnvelope.decay) }}</span>
        </div>
        <div class="sd-row">
          <span class="sd-label">Sustain</span>
          <input v-model.number="patch.filterEnvelope.sustain" class="sd-slider" type="range" min="0" max="1" step="0.01" />
          <span class="sd-val">{{ patch.filterEnvelope.sustain.toFixed(2) }}</span>
        </div>
        <div class="sd-row">
          <span class="sd-label">Release</span>
          <input v-model.number="patch.filterEnvelope.release" class="sd-slider" type="range" min="0.001" max="4" step="0.001" />
          <span class="sd-val">{{ secs(patch.filterEnvelope.release) }}</span>
        </div>
        <div class="sd-row">
          <span class="sd-label">Base</span>
          <input v-model.number="baseFreqPos" class="sd-slider" type="range" min="0" max="1000" step="1" />
          <span class="sd-val">{{ patch.filterEnvelope.baseFrequency }} Hz</span>
        </div>
        <div class="sd-row">
          <span class="sd-label">Depth</span>
          <input v-model.number="patch.filterEnvelope.octaves" class="sd-slider" type="range" min="0" max="7" step="0.1" />
          <span class="sd-val">{{ patch.filterEnvelope.octaves.toFixed(1) }} oct</span>
        </div>
      </section>

      <!-- ── Pitch envelope (mono voices) ───────────────────────────────────── -->
      <section v-if="isMono">
        <div class="sd-head-row">
          <h3>Pitch Envelope</h3>
          <label class="sd-toggle">
            <input type="checkbox" :checked="hasPitchEnv" @change="togglePitchEnv(($event.target as HTMLInputElement).checked)" />
            {{ hasPitchEnv ? 'On' : 'Off' }}
          </label>
        </div>
        <p class="sd-hint">A per-note pitch drop — the note starts higher and falls to pitch. The 808/kick attack "click".</p>
        <template v-if="patch.pitchEnvelope">
          <div class="sd-row">
            <span class="sd-label">Depth</span>
            <input v-model.number="patch.pitchEnvelope.semitones" class="sd-slider" type="range" min="0" max="24" step="1" />
            <span class="sd-val">+{{ patch.pitchEnvelope.semitones }} st</span>
          </div>
          <div class="sd-row">
            <span class="sd-label">Decay</span>
            <input v-model.number="patch.pitchEnvelope.decay" class="sd-slider" type="range" min="0.01" max="0.5" step="0.005" />
            <span class="sd-val">{{ Math.round(patch.pitchEnvelope.decay * 1000) }} ms</span>
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

      <!-- ── LFO (poly voices) ──────────────────────────────────────────────── -->
      <section v-if="!isMono">
        <div class="sd-head-row">
          <h3>LFO</h3>
          <label class="sd-toggle">
            <input type="checkbox" :checked="hasLfo" @change="toggleLfo(($event.target as HTMLInputElement).checked)" />
            {{ hasLfo ? 'On' : 'Off' }}
          </label>
        </div>
        <template v-if="patch.lfo">
          <div class="sd-row">
            <span class="sd-label">Target</span>
            <select class="sd-input" :value="patch.lfo.destination" @change="setLfoDest(($event.target as HTMLSelectElement).value)">
              <option v-if="hasFilter" value="filter">filter cutoff</option>
              <option value="amp">amp (tremolo)</option>
            </select>
          </div>
          <div class="sd-row">
            <span class="sd-label">Wave</span>
            <select class="sd-input" :value="patch.lfo.wave" @change="setLfoWave(($event.target as HTMLSelectElement).value)">
              <option value="sine">sine</option>
              <option value="triangle">triangle</option>
              <option value="sawtooth">sawtooth</option>
              <option value="square">square</option>
            </select>
          </div>
          <div class="sd-row">
            <span class="sd-label">Sync</span>
            <label class="sd-toggle"><input v-model="patch.lfo.sync" type="checkbox" /> tempo-synced</label>
          </div>
          <div v-if="!patch.lfo.sync" class="sd-row">
            <span class="sd-label">Rate</span>
            <input v-model.number="patch.lfo.rateHz" class="sd-slider" type="range" min="0.1" max="20" step="0.1" />
            <span class="sd-val">{{ patch.lfo.rateHz.toFixed(1) }} Hz</span>
          </div>
          <div v-else class="sd-row">
            <span class="sd-label">Rate</span>
            <select class="sd-input" :value="patch.lfo.syncRate" @change="setSyncRate(($event.target as HTMLSelectElement).value)">
              <option v-for="r in SYNC_RATES" :key="r" :value="r">{{ r }}</option>
            </select>
          </div>
          <div class="sd-row">
            <span class="sd-label">Depth</span>
            <input v-model.number="patch.lfo.depth" class="sd-slider" type="range" min="0" max="1" step="0.01" />
            <span class="sd-val">{{ Math.round(patch.lfo.depth * 100) }}%</span>
          </div>
        </template>
        <p v-else class="sd-hint">A slow oscillator to wobble the filter cutoff or pulse the volume.</p>
      </section>

      <!-- ── FX (all voices) ────────────────────────────────────────────────── -->
      <section>
        <h3>FX</h3>

        <div class="sd-head-row sd-fx-head">
          <span class="sd-fx-name">Drive</span>
          <label class="sd-toggle"><input type="checkbox" :checked="hasFx('drive')" @change="toggleFx('drive', ($event.target as HTMLInputElement).checked)" /> {{ hasFx('drive') ? 'On' : 'Off' }}</label>
        </div>
        <template v-if="patch.fx?.drive">
          <div class="sd-row"><span class="sd-label">Amount</span><input v-model.number="patch.fx.drive.amount" class="sd-slider" type="range" min="0" max="1" step="0.01" /><span class="sd-val">{{ pct(patch.fx.drive.amount) }}</span></div>
          <div class="sd-row"><span class="sd-label">Mix</span><input v-model.number="patch.fx.drive.wet" class="sd-slider" type="range" min="0" max="1" step="0.01" /><span class="sd-val">{{ pct(patch.fx.drive.wet) }}</span></div>
        </template>

        <div class="sd-head-row sd-fx-head">
          <span class="sd-fx-name">Bitcrusher</span>
          <label class="sd-toggle"><input type="checkbox" :checked="hasFx('bitcrusher')" @change="toggleFx('bitcrusher', ($event.target as HTMLInputElement).checked)" /> {{ hasFx('bitcrusher') ? 'On' : 'Off' }}</label>
        </div>
        <template v-if="patch.fx?.bitcrusher">
          <div class="sd-row"><span class="sd-label">Bits</span><input v-model.number="patch.fx.bitcrusher.bits" class="sd-slider" type="range" min="1" max="16" step="1" /><span class="sd-val">{{ patch.fx.bitcrusher.bits }}</span></div>
        </template>

        <div class="sd-head-row sd-fx-head">
          <span class="sd-fx-name">Chorus</span>
          <label class="sd-toggle"><input type="checkbox" :checked="hasFx('chorus')" @change="toggleFx('chorus', ($event.target as HTMLInputElement).checked)" /> {{ hasFx('chorus') ? 'On' : 'Off' }}</label>
        </div>
        <template v-if="patch.fx?.chorus">
          <div class="sd-row"><span class="sd-label">Rate</span><input v-model.number="patch.fx.chorus.frequency" class="sd-slider" type="range" min="0.1" max="8" step="0.1" /><span class="sd-val">{{ patch.fx.chorus.frequency.toFixed(1) }} Hz</span></div>
          <div class="sd-row"><span class="sd-label">Depth</span><input v-model.number="patch.fx.chorus.depth" class="sd-slider" type="range" min="0" max="1" step="0.01" /><span class="sd-val">{{ pct(patch.fx.chorus.depth) }}</span></div>
          <div class="sd-row"><span class="sd-label">Mix</span><input v-model.number="patch.fx.chorus.wet" class="sd-slider" type="range" min="0" max="1" step="0.01" /><span class="sd-val">{{ pct(patch.fx.chorus.wet) }}</span></div>
        </template>

        <div class="sd-head-row sd-fx-head">
          <span class="sd-fx-name">Vibrato</span>
          <label class="sd-toggle"><input type="checkbox" :checked="hasFx('vibrato')" @change="toggleFx('vibrato', ($event.target as HTMLInputElement).checked)" /> {{ hasFx('vibrato') ? 'On' : 'Off' }}</label>
        </div>
        <template v-if="patch.fx?.vibrato">
          <div class="sd-row"><span class="sd-label">Rate</span><input v-model.number="patch.fx.vibrato.frequency" class="sd-slider" type="range" min="0.1" max="12" step="0.1" /><span class="sd-val">{{ patch.fx.vibrato.frequency.toFixed(1) }} Hz</span></div>
          <div class="sd-row"><span class="sd-label">Depth</span><input v-model.number="patch.fx.vibrato.depth" class="sd-slider" type="range" min="0" max="1" step="0.01" /><span class="sd-val">{{ pct(patch.fx.vibrato.depth) }}</span></div>
          <div class="sd-row"><span class="sd-label">Mix</span><input v-model.number="patch.fx.vibrato.wet" class="sd-slider" type="range" min="0" max="1" step="0.01" /><span class="sd-val">{{ pct(patch.fx.vibrato.wet) }}</span></div>
        </template>

        <div class="sd-head-row sd-fx-head">
          <span class="sd-fx-name">Delay</span>
          <label class="sd-toggle"><input type="checkbox" :checked="hasFx('delay')" @change="toggleFx('delay', ($event.target as HTMLInputElement).checked)" /> {{ hasFx('delay') ? 'On' : 'Off' }}</label>
        </div>
        <template v-if="patch.fx?.delay">
          <div class="sd-row"><span class="sd-label">Sync</span><label class="sd-toggle"><input v-model="patch.fx.delay.sync" type="checkbox" /> tempo-synced</label></div>
          <div v-if="!patch.fx.delay.sync" class="sd-row"><span class="sd-label">Time</span><input v-model.number="patch.fx.delay.time" class="sd-slider" type="range" min="0.01" max="1" step="0.01" /><span class="sd-val">{{ Math.round(patch.fx.delay.time * 1000) }} ms</span></div>
          <div v-else class="sd-row"><span class="sd-label">Time</span><select class="sd-input" :value="patch.fx.delay.syncTime" @change="setDelayTime(($event.target as HTMLSelectElement).value)"><option v-for="t in DELAY_TIMES" :key="t" :value="t">{{ t }}</option></select></div>
          <div class="sd-row"><span class="sd-label">Feedback</span><input v-model.number="patch.fx.delay.feedback" class="sd-slider" type="range" min="0" max="0.9" step="0.01" /><span class="sd-val">{{ pct(patch.fx.delay.feedback) }}</span></div>
          <div class="sd-row"><span class="sd-label">Mix</span><input v-model.number="patch.fx.delay.wet" class="sd-slider" type="range" min="0" max="1" step="0.01" /><span class="sd-val">{{ pct(patch.fx.delay.wet) }}</span></div>
        </template>

        <div class="sd-head-row sd-fx-head">
          <span class="sd-fx-name">Reverb</span>
          <label class="sd-toggle"><input type="checkbox" :checked="hasFx('reverb')" @change="toggleFx('reverb', ($event.target as HTMLInputElement).checked)" /> {{ hasFx('reverb') ? 'On' : 'Off' }}</label>
        </div>
        <template v-if="patch.fx?.reverb">
          <div class="sd-row"><span class="sd-label">Decay</span><input v-model.number="patch.fx.reverb.decay" class="sd-slider" type="range" min="0.1" max="8" step="0.1" /><span class="sd-val">{{ patch.fx.reverb.decay.toFixed(1) }} s</span></div>
          <div class="sd-row"><span class="sd-label">Mix</span><input v-model.number="patch.fx.reverb.wet" class="sd-slider" type="range" min="0" max="1" step="0.01" /><span class="sd-val">{{ pct(patch.fx.reverb.wet) }}</span></div>
        </template>
      </section>

      <!-- ── Keyboard ───────────────────────────────────────────────────────── -->
      <section>
        <div class="sd-head-row">
          <h3>Audition</h3>
          <div class="sd-oct">
            <button class="sd-mini" title="Octave down" @click="octaveBase = Math.max(0, octaveBase - 1)">– oct</button>
            <span class="sd-oct-label">C{{ octaveBase }}–B{{ octaveBase + 1 }}</span>
            <button class="sd-mini" title="Octave up" @click="octaveBase = Math.min(7, octaveBase + 1)">+ oct</button>
          </div>
        </div>
        <p v-if="isMono" class="sd-hint">Bass/808 patches live low — drop to C1–C2 to hear the sub.</p>
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

      <!-- ── Library: save / load ───────────────────────────────────────────── -->
      <section>
        <h3>Library</h3>
        <div class="sd-save-row">
          <input v-model="saveName" class="sd-input" type="text" placeholder="Patch name" />
          <button class="sd-btn" :disabled="!saveName.trim()" @click="doSave">Save</button>
        </div>
        <p v-if="!patches.length" class="sd-hint">No saved patches yet — design a voice and save it here.</p>
        <ul v-else class="sd-list">
          <li v-for="p in patches" :key="p.id" class="sd-item">
            <span class="sd-item-name">{{ p.name }}</span>
            <button class="sd-mini" @click="loadSaved(p.id)">Load</button>
            <button class="sd-del" title="Delete" @click="deletePatch(p.id)">Delete</button>
          </li>
        </ul>
      </section>

      <!-- ── Assign to parts ────────────────────────────────────────────────── -->
      <section>
        <div class="sd-head-row">
          <h3>Assign to part</h3>
          <div class="sd-scope">
            <label><input v-model="scope" type="radio" value="all" /> All styles</label>
            <label><input v-model="scope" type="radio" value="style" /> This style</label>
          </div>
        </div>
        <p class="sd-hint">
          Assigned patches replace that part's built-in voice — in the live preview and in
          audio exports. Pick a built-in or one of your saved patches.
        </p>
        <div v-if="styleKit.length" class="sd-kit">
          <span class="sd-kit-text">Suggested: {{ styleKit.map(k => partLabel(k.part) + ' → ' + k.label).join(', ') }}</span>
          <button class="sd-mini" @click="applyKit">Apply to this style</button>
        </div>
        <div v-for="part in PATCHABLE_PARTS" :key="part" class="sd-assign-row">
          <span class="sd-label">{{ partLabel(part) }}</span>
          <select class="sd-input" :value="currentAssign(part) ?? ''" @change="onAssign(part, ($event.target as HTMLSelectElement).value)">
            <option value="">— Style default —</option>
            <optgroup label="Built-in patches">
              <option v-for="o in BUILTIN_OPTIONS" :key="o.id" :value="o.id">{{ o.label }}</option>
            </optgroup>
            <optgroup v-if="patches.length" label="Saved">
              <option v-for="p in patches" :key="p.id" :value="p.id">{{ p.name }}</option>
            </optgroup>
          </select>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue'
import { useSynthDesigner } from '../composables/useSynthDesigner'
import { useSynthPatches, PATCHABLE_PARTS, builtinPatchOptions, styleKitFor } from '../composables/useSynthPatches'
import { useStyleCatalog } from '../composables/useStyleCatalog'
import type { PlayerPart } from '../composables/useMidiPlayer'
import { auditionPatchNote, disposeSynthPreview } from '../soundfonts/audition'
import {
  type SynthPatch, type OscillatorWave, type FilterType, type FilterRolloff,
  type LfoDestination, type LfoWave, type FxChain,
  BUILTIN_PATCHES,
} from '../soundfonts/synthPatch'

const { open, close } = useSynthDesigner()

// The preset menu is every built-in patch (registry is the single source of truth).
const PRESETS: { id: string; label: string; patch: SynthPatch }[] =
  Object.entries(BUILTIN_PATCHES).map(([id, e]) => ({ id, label: e.label, patch: e.patch }))

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

// ── Filter ────────────────────────────────────────────────────────────────────
// A poly voice carries an OPTIONAL external filter; the mono (bass) voice's filter is
// intrinsic to its MonoSynth and driven by the filter envelope, so its cutoff isn't a
// free control and it can't be switched off.
const isMono = computed(() => patch.value.voice === 'mono')
const hasFilter = computed(() => !!patch.value.filter)

function toggleFilter(on: boolean) {
  if (on) {
    if (!patch.value.filter) patch.value.filter = { type: 'lowpass', frequency: 2000, Q: 1, rolloff: -12 }
  } else {
    delete patch.value.filter
  }
}
function setFilterType(t: string) { if (patch.value.filter) patch.value.filter.type = t as FilterType }
function setRolloff(r: string) { if (patch.value.filter) patch.value.filter.rolloff = Number(r) as FilterRolloff }

// Cutoff / base-frequency sliders travel a log scale (0..1000 → 20..12000 Hz) so the
// low end where cutoff matters most isn't crammed into a few pixels.
const CUT_MIN = 20, CUT_MAX = 12000
const freqToPos = (f: number) => Math.round(1000 * Math.log(f / CUT_MIN) / Math.log(CUT_MAX / CUT_MIN))
const posToFreq = (p: number) => Math.round(CUT_MIN * (CUT_MAX / CUT_MIN) ** (p / 1000))

const cutoffPos = computed({
  get: () => (patch.value.filter?.frequency !== undefined ? freqToPos(patch.value.filter.frequency) : 0),
  set: (p: number) => { if (patch.value.filter) patch.value.filter.frequency = posToFreq(p) },
})
const baseFreqPos = computed({
  get: () => (patch.value.filterEnvelope ? freqToPos(patch.value.filterEnvelope.baseFrequency) : 0),
  set: (p: number) => { if (patch.value.filterEnvelope) patch.value.filterEnvelope.baseFrequency = posToFreq(p) },
})

// ── Pitch envelope (mono voices only) ─────────────────────────────────────────
const hasPitchEnv = computed(() => !!patch.value.pitchEnvelope)
function togglePitchEnv(on: boolean) {
  if (on) { if (!patch.value.pitchEnvelope) patch.value.pitchEnvelope = { semitones: 8, decay: 0.06 } }
  else delete patch.value.pitchEnvelope
}

// ── LFO ───────────────────────────────────────────────────────────────────────
// One LFO, poly voices only (the mono bass already moves via its filter envelope).
const SYNC_RATES = ['1n', '2n', '4n', '4n.', '8n', '8n.', '8t', '16n']
const hasLfo = computed(() => !!patch.value.lfo)

function toggleLfo(on: boolean) {
  if (on) {
    if (!patch.value.lfo) patch.value.lfo = {
      destination: patch.value.filter ? 'filter' : 'amp',
      wave: 'sine', rateHz: 5, sync: false, syncRate: '8n', depth: 0.5,
    }
  } else {
    delete patch.value.lfo
  }
}
function setLfoDest(d: string) { if (patch.value.lfo) patch.value.lfo.destination = d as LfoDestination }
function setLfoWave(w: string) { if (patch.value.lfo) patch.value.lfo.wave = w as LfoWave }
function setSyncRate(r: string) { if (patch.value.lfo) patch.value.lfo.syncRate = r }

// ── FX ────────────────────────────────────────────────────────────────────────
// Each effect is an independent toggle over patch.fx; the chain ORDER is fixed by
// patchToNodeSpec, so the UI only owns which effects exist and their params.
const DELAY_TIMES = ['16n', '8t', '8n', '8n.', '4n', '4n.', '2n']
const FX_DEFAULTS: { [K in keyof FxChain]-?: NonNullable<FxChain[K]> } = {
  drive: { amount: 0.3, wet: 0.5 },
  bitcrusher: { bits: 8 },
  chorus: { frequency: 1.5, depth: 0.5, wet: 0.4 },
  vibrato: { frequency: 5, depth: 0.1, wet: 0.8 },
  delay: { time: 0.25, sync: false, syncTime: '8n', feedback: 0.3, wet: 0.3 },
  reverb: { decay: 2, wet: 0.3 },
}
const hasFx = (k: keyof FxChain) => !!patch.value.fx?.[k]
function toggleFx(key: keyof FxChain, on: boolean) {
  if (!patch.value.fx) patch.value.fx = {}
  const fx = patch.value.fx
  if (on) {
    if (!fx[key]) Object.assign(fx, { [key]: structuredClone(FX_DEFAULTS[key]) })
  } else {
    delete fx[key]
    if (Object.keys(fx).length === 0) delete patch.value.fx
  }
}
function setDelayTime(t: string) { if (patch.value.fx?.delay) patch.value.fx.delay.syncTime = t }
const pct = (v: number) => `${Math.round(v * 100)}%`

// ── Library + assignment ──────────────────────────────────────────────────────
const { patches, savePatch, deletePatch, assignPatch, getPatch, assignedId, applyStyleKit } = useSynthPatches()
const { activeStyleId } = useStyleCatalog()

const BUILTIN_OPTIONS = builtinPatchOptions()
const styleKit = computed(() => styleKitFor(activeStyleId.value ?? undefined))
function applyKit() {
  if (activeStyleId.value) { applyStyleKit(activeStyleId.value); scope.value = 'style' }
}

const saveName = ref('')
const scope = ref<'all' | 'style'>('all')

function doSave() {
  const saved = savePatch(saveName.value, patch.value)
  saveName.value = saved.name   // keep the name so a re-save updates in place
}
function loadSaved(id: string) {
  const s = getPatch(id)
  if (s) { patch.value = clone(s.patch); saveName.value = s.name }
}
function onAssign(part: PlayerPart, id: string) {
  assignPatch(part, id || null, scope.value === 'style' ? (activeStyleId.value ?? undefined) : undefined)
}
function currentAssign(part: PlayerPart): string | undefined {
  return assignedId(activeStyleId.value ?? undefined, part, scope.value)
}
function partLabel(p: PlayerPart): string {
  return p === 'counter_melody' ? 'Counter-melody' : p.charAt(0).toUpperCase() + p.slice(1)
}

function play(note: string) {
  void auditionPatchNote(patch.value, note)
}

// ── Keyboard layout: two octaves from octaveBase, black keys over the white row ──
// Bass/808 patches only reveal their sub character down at C1–C2, so the base octave
// is adjustable and defaults lower for mono voices.
const WHITE_NAMES = ['C', 'D', 'E', 'F', 'G', 'A', 'B']
const BLACK_DEFS = [{ name: 'C#', pos: 1 }, { name: 'D#', pos: 2 }, { name: 'F#', pos: 4 }, { name: 'G#', pos: 5 }, { name: 'A#', pos: 6 }]
const totalWhite = 2 * WHITE_NAMES.length
const octaveBase = ref(isMono.value ? 1 : 3)
const octaves = computed(() => [octaveBase.value, octaveBase.value + 1])
const whiteKeys = computed(() => octaves.value.flatMap(o => WHITE_NAMES.map(n => ({ note: `${n}${o}` }))))
const blackKeys = computed(() => octaves.value.flatMap((o, oi) => BLACK_DEFS.map(b => ({ note: `${b.name}${o}`, pos: oi * WHITE_NAMES.length + b.pos }))))

// Loading a preset of a different voice type nudges the octave to a sensible register.
watch(() => patch.value.voice, (v) => { octaveBase.value = v === 'mono' ? 1 : 3 })

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
.sd-toggle { display: flex; align-items: center; gap: 0.35rem; font-size: 0.78rem; color: var(--text-faint); cursor: pointer; }
.sd-toggle input { accent-color: var(--accent); }
.sd-fx-head { margin-top: 0.6rem; padding-top: 0.5rem; border-top: 1px dashed var(--border); }
.sd-fx-head:first-of-type { margin-top: 0; padding-top: 0; border-top: none; }
.sd-fx-name { font-size: 0.82rem; font-weight: 600; }
.sd-save-row { display: flex; gap: 0.5rem; align-items: center; margin-bottom: 0.5rem; }
.sd-save-row .sd-input { flex: 1; }
.sd-btn {
  font: inherit; padding: 0.4rem 0.9rem; border: 1px solid var(--border);
  border-radius: 6px; background: var(--accent); color: var(--accent-contrast, #fff); cursor: pointer;
}
.sd-btn:disabled { opacity: 0.5; cursor: default; }
.sd-list { list-style: none; margin: 0; padding: 0; }
.sd-item { display: flex; align-items: center; gap: 0.5rem; padding: 0.3rem 0; border-bottom: 1px solid var(--border); }
.sd-item-name { flex: 1; font-weight: 600; font-size: 0.85rem; }
.sd-mini {
  font-size: 0.72rem; background: none; border: 1px solid var(--border);
  border-radius: 5px; color: var(--text-faint); cursor: pointer; padding: 0.2rem 0.5rem;
}
.sd-mini:hover { color: var(--text); border-color: var(--accent); }
.sd-del { font-size: 0.72rem; background: none; border: 1px solid var(--border); border-radius: 5px; color: var(--text-faint); cursor: pointer; padding: 0.2rem 0.5rem; }
.sd-del:hover { color: #e66; border-color: #e66; }
.sd-scope { display: flex; gap: 0.7rem; font-size: 0.76rem; color: var(--text-faint); }
.sd-scope label { display: flex; align-items: center; gap: 0.25rem; cursor: pointer; }
.sd-assign-row { display: grid; grid-template-columns: 110px 1fr; align-items: center; gap: 0.6rem; margin-bottom: 0.4rem; }
.sd-kit { display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.6rem; padding: 0.4rem 0.5rem; border: 1px dashed var(--border); border-radius: 6px; }
.sd-kit-text { flex: 1; font-size: 0.78rem; color: var(--text-faint); }
.sd-oct { display: flex; align-items: center; gap: 0.4rem; }
.sd-oct-label { font-size: 0.75rem; color: var(--text-faint); font-variant-numeric: tabular-nums; min-width: 56px; text-align: center; }
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
