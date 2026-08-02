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
  Drum designer — the drum-side analog of SynthDesigner.vue. Shapes a synthesized
  kick/snare/hat/etc from their raw tone parameters (pitch decay, sub layer,
  tone/noise mix, FM harmonicity — see synthDrums.ts, DrumKitPatch) and auditions
  on a pad grid instead of a keyboard, since drums aren't played chromatically.
  Open/closed hat and crash/ride share their decay shape with the closed hat and
  crash sliders (scaled internally by synthDrums.ts) rather than exposing four
  near-duplicate decay controls.
-->
<template>
  <div v-if="open" class="dd-overlay" @click.self="close" @keydown.esc="close">
    <div class="dd-modal" role="dialog" aria-label="Drum designer">
      <header class="dd-header">
        <h2>Drum Designer</h2>
        <button class="dd-x" title="Close" @click="close">✕</button>
      </header>

      <!-- ── Preset ─────────────────────────────────────────────────────────── -->
      <section class="dd-first">
        <div class="dd-head-row">
          <h3>Preset</h3>
          <div class="dd-browse">
            <button class="dd-mini" title="Previous" @click="browse(-1)">◀</button>
            <select v-model="selectedPreset" class="dd-input dd-preset" @change="loadPreset(selectedPreset)">
              <option v-for="p in PRESETS" :key="p.id" :value="p.id">{{ p.label }}</option>
            </select>
            <button class="dd-mini" title="Next" @click="browse(1)">▶</button>
          </div>
        </div>
        <p class="dd-hint">
          The seven built-in kits, as editable patches — shape each piece's raw tone and
          audition it on the pads or the loop below. Editing a control marks the kit as
          modified; ◀ ▶ step through built-ins and saved kits — handy for A/B-ing a feel
          while the loop plays.
        </p>
      </section>

      <!-- ── Kick ───────────────────────────────────────────────────────────── -->
      <section>
        <h3>Kick</h3>
        <div class="dd-row">
          <span class="dd-label">Note</span>
          <select class="dd-input" v-model="patch.kickNote"><option v-for="n in NOTES" :key="n" :value="n">{{ n }}</option></select>
          <span class="dd-val"></span>
        </div>
        <div class="dd-row">
          <span class="dd-label">Body wave</span>
          <select class="dd-input" v-model="patch.kickOscType"><option v-for="w in WAVES" :key="w" :value="w">{{ w }}</option></select>
          <span class="dd-val"></span>
        </div>
        <div class="dd-row">
          <span class="dd-label">Pitch decay</span>
          <input v-model.number="patch.kickPitchDecay" class="dd-slider" type="range" min="0.005" max="0.2" step="0.001" />
          <span class="dd-val">{{ Math.round(patch.kickPitchDecay * 1000) }} ms</span>
        </div>
        <div class="dd-row">
          <span class="dd-label">Sweep</span>
          <input v-model.number="patch.kickOctaves" class="dd-slider" type="range" min="1" max="8" step="0.1" />
          <span class="dd-val">{{ patch.kickOctaves.toFixed(1) }} oct</span>
        </div>
        <div class="dd-row">
          <span class="dd-label">Decay</span>
          <input v-model.number="patch.kickDecay" class="dd-slider" type="range" min="0.05" max="1.5" step="0.01" />
          <span class="dd-val">{{ secs(patch.kickDecay) }}</span>
        </div>
        <div class="dd-row">
          <span class="dd-label">Click</span>
          <select class="dd-input" v-model="patch.clickNoiseType"><option v-for="n in NOISES" :key="n" :value="n">{{ n }}</option></select>
          <span class="dd-val"></span>
        </div>
      </section>

      <!-- ── Sub layer ──────────────────────────────────────────────────────── -->
      <section>
        <h3>Sub layer</h3>
        <p class="dd-hint">The dedicated boom underneath the kick body.</p>
        <div class="dd-row">
          <span class="dd-label">Note</span>
          <select class="dd-input" v-model="patch.subNote"><option v-for="n in NOTES" :key="n" :value="n">{{ n }}</option></select>
          <span class="dd-val"></span>
        </div>
        <div class="dd-row">
          <span class="dd-label">Wave</span>
          <select class="dd-input" v-model="patch.subOscType"><option v-for="w in WAVES" :key="w" :value="w">{{ w }}</option></select>
          <span class="dd-val"></span>
        </div>
        <div class="dd-row">
          <span class="dd-label">Decay</span>
          <input v-model.number="patch.subDecay" class="dd-slider" type="range" min="0.05" max="1.5" step="0.01" />
          <span class="dd-val">{{ secs(patch.subDecay) }}</span>
        </div>
        <div class="dd-row">
          <span class="dd-label">Level</span>
          <input v-model.number="patch.subLevel" class="dd-slider" type="range" min="-30" max="0" step="0.5" />
          <span class="dd-val">{{ patch.subLevel }} dB</span>
        </div>
      </section>

      <!-- ── Snare ──────────────────────────────────────────────────────────── -->
      <section>
        <h3>Snare</h3>
        <div class="dd-row">
          <span class="dd-label">Tone freq</span>
          <input v-model.number="patch.snareToneFreq" class="dd-slider" type="range" min="80" max="500" step="1" />
          <span class="dd-val">{{ patch.snareToneFreq }} Hz</span>
        </div>
        <div class="dd-row">
          <span class="dd-label">Tone wave</span>
          <select class="dd-input" v-model="patch.snareToneOscType"><option v-for="w in WAVES" :key="w" :value="w">{{ w }}</option></select>
          <span class="dd-val"></span>
        </div>
        <div class="dd-row">
          <span class="dd-label">Tone mix</span>
          <input v-model.number="patch.snareToneMix" class="dd-slider" type="range" min="0" max="1" step="0.01" />
          <span class="dd-val">{{ pct(patch.snareToneMix) }}</span>
        </div>
        <div class="dd-row">
          <span class="dd-label">Noise</span>
          <select class="dd-input" v-model="patch.snareNoiseType"><option v-for="n in NOISES" :key="n" :value="n">{{ n }}</option></select>
          <span class="dd-val"></span>
        </div>
        <div class="dd-row">
          <span class="dd-label">Noise decay</span>
          <input v-model.number="patch.snareNoiseDecay" class="dd-slider" type="range" min="0.02" max="0.5" step="0.005" />
          <span class="dd-val">{{ secs(patch.snareNoiseDecay) }}</span>
        </div>
        <div class="dd-row">
          <span class="dd-label">Buzz mix</span>
          <input v-model.number="patch.snareBuzzMix" class="dd-slider" type="range" min="0" max="1" step="0.01" />
          <span class="dd-val">{{ pct(patch.snareBuzzMix) }}</span>
        </div>
      </section>

      <!-- ── Clap ───────────────────────────────────────────────────────────── -->
      <section>
        <h3>Clap</h3>
        <div class="dd-row">
          <span class="dd-label">Noise</span>
          <select class="dd-input" v-model="patch.clapNoiseType"><option v-for="n in NOISES" :key="n" :value="n">{{ n }}</option></select>
          <span class="dd-val"></span>
        </div>
      </section>

      <!-- ── Hats & cymbals ─────────────────────────────────────────────────── -->
      <section>
        <h3>Hats &amp; cymbals</h3>
        <p class="dd-hint">Open hat, crash and ride scale off the closed-hat/crash settings below.</p>
        <div class="dd-row">
          <span class="dd-label">Hat freq</span>
          <input v-model.number="patch.hatFreq" class="dd-slider" type="range" min="150" max="900" step="1" />
          <span class="dd-val">{{ patch.hatFreq }} Hz</span>
        </div>
        <div class="dd-row">
          <span class="dd-label">Hat decay</span>
          <input v-model.number="patch.hatDecay" class="dd-slider" type="range" min="0.01" max="0.15" step="0.001" />
          <span class="dd-val">{{ Math.round(patch.hatDecay * 1000) }} ms</span>
        </div>
        <div class="dd-row">
          <span class="dd-label">Harmonicity</span>
          <input v-model.number="patch.hatHarmonicity" class="dd-slider" type="range" min="1" max="10" step="0.1" />
          <span class="dd-val">{{ patch.hatHarmonicity.toFixed(1) }}</span>
        </div>
        <div class="dd-row">
          <span class="dd-label">Mod index</span>
          <input v-model.number="patch.hatModIndex" class="dd-slider" type="range" min="1" max="60" step="1" />
          <span class="dd-val">{{ patch.hatModIndex }}</span>
        </div>
        <div class="dd-row">
          <span class="dd-label">Crash decay</span>
          <input v-model.number="patch.cymbalDecay" class="dd-slider" type="range" min="0.3" max="4" step="0.05" />
          <span class="dd-val">{{ secs(patch.cymbalDecay) }}</span>
        </div>
        <div class="dd-row">
          <span class="dd-label">Ride decay</span>
          <input v-model.number="patch.rideDecay" class="dd-slider" type="range" min="0.2" max="3" step="0.05" />
          <span class="dd-val">{{ secs(patch.rideDecay) }}</span>
        </div>
      </section>

      <!-- ── Toms ───────────────────────────────────────────────────────────── -->
      <section>
        <h3>Toms</h3>
        <div class="dd-row">
          <span class="dd-label">Wave</span>
          <select class="dd-input" v-model="patch.tomOscType"><option v-for="w in WAVES" :key="w" :value="w">{{ w }}</option></select>
          <span class="dd-val"></span>
        </div>
      </section>

      <!-- ── Kit tone ───────────────────────────────────────────────────────── -->
      <section>
        <h3>Kit tone</h3>
        <div class="dd-row">
          <span class="dd-label">Warmth</span>
          <input v-model.number="patch.masterLPF" class="dd-slider" type="range" min="500" max="20000" step="100" />
          <span class="dd-val">{{ patch.masterLPF >= 20000 ? 'off' : `${patch.masterLPF} Hz` }}</span>
        </div>
        <div class="dd-row">
          <span class="dd-label">Drive</span>
          <input v-model.number="patch.drive" class="dd-slider" type="range" min="0" max="0.5" step="0.01" />
          <span class="dd-val">{{ pct(patch.drive) }}</span>
        </div>
        <div class="dd-row">
          <span class="dd-label">Humanize</span>
          <input v-model.number="patch.humanize" class="dd-slider" type="range" min="0" max="1" step="0.01" />
          <span class="dd-val">{{ pct(patch.humanize) }}</span>
        </div>
        <p class="dd-hint">Humanize jitters pitch/level per hit and pan on hats/cymbals — real kits never hit identically twice.</p>
      </section>

      <!-- ── Sample base ────────────────────────────────────────────────────── -->
      <section>
        <h3>Sample base</h3>
        <p v-if="!ciSupported" class="dd-hint">
          Blending in an uploaded sample needs the GenreGrid desktop app — unavailable in the browser build.
        </p>
        <template v-else>
          <p class="dd-hint">
            Blend a real sample under this synth kit for extra realism on the pieces it
            covers. Upload/organize sample kits in the Instruments panel (🎹) — pick one here.
          </p>
          <div class="dd-row">
            <span class="dd-label">Kit</span>
            <select class="dd-input" v-model="sampleKitIdModel">
              <option value="">— None (pure synth) —</option>
              <option v-for="inst in drumSampleKits" :key="inst.id" :value="inst.id">{{ inst.name }}</option>
            </select>
            <span class="dd-val"></span>
          </div>
          <div v-if="patch.sampleKitId" class="dd-row">
            <span class="dd-label">Blend</span>
            <input v-model.number="patch.sampleBlend" class="dd-slider" type="range" min="0" max="1" step="0.01" />
            <span class="dd-val">{{ pct(patch.sampleBlend) }}</span>
          </div>
        </template>
      </section>

      <!-- ── Pads ───────────────────────────────────────────────────────────── -->
      <section>
        <div class="dd-head-row">
          <h3>Audition</h3>
          <div class="dd-loop">
            <button class="dd-btn dd-loop-btn" :class="{ 'is-on': isLooping }" @click="toggleLoop">
              {{ isLooping ? '■ Stop' : '▶ Loop' }}
            </button>
            <input v-model.number="tempo" class="dd-tempo" type="range" min="60" max="160" step="1" title="Loop tempo" />
            <span class="dd-val">{{ tempo }} bpm</span>
          </div>
        </div>
        <p class="dd-hint">
          Loop plays a demo groove through the kit under design — slower to hear decay
          tails, faster to hear how it holds together busy. Pads still work while it plays.
        </p>
        <div class="dd-pads">
          <button v-for="pad in PADS" :key="pad.pitch" class="dd-pad" @mousedown="play(pad.pitch)">{{ pad.label }}</button>
        </div>
      </section>

      <!-- ── Library: save / load ───────────────────────────────────────────── -->
      <section>
        <h3>Library</h3>
        <div class="dd-save-row">
          <input v-model="saveName" class="dd-input" type="text" placeholder="Kit name" />
          <button class="dd-btn" :disabled="!saveName.trim()" @click="doSave">Save</button>
        </div>
        <p v-if="!kits.length" class="dd-hint">No saved kits yet — design a sound and save it here.</p>
        <ul v-else class="dd-list">
          <li v-for="k in kits" :key="k.id" class="dd-item">
            <span class="dd-item-name">{{ k.name }}</span>
            <button class="dd-mini" @click="loadSaved(k.id)">Load</button>
            <button class="dd-del" title="Delete" @click="deleteKit(k.id)">Delete</button>
          </li>
        </ul>
      </section>

      <!-- ── Assign ─────────────────────────────────────────────────────────── -->
      <section>
        <div class="dd-head-row">
          <h3>Assign</h3>
          <div class="dd-scope">
            <label><input v-model="scope" type="radio" value="all" /> All styles</label>
            <label><input v-model="scope" type="radio" value="style" /> This style</label>
          </div>
        </div>
        <p class="dd-hint">
          An assigned kit replaces the style's built-in drum character — in the live
          preview and in audio exports. This is separate from an uploaded sample kit
          (Instruments panel); both can apply at once, with samples taking each piece
          they cover.
        </p>
        <select class="dd-input" style="width: 100%" :value="currentAssign ?? ''" @change="onAssign(($event.target as HTMLSelectElement).value)">
          <option value="">— Style default —</option>
          <optgroup label="Built-in kits">
            <option v-for="o in BUILTIN_OPTIONS" :key="o.id" :value="o.id">{{ o.label }}</option>
          </optgroup>
          <optgroup v-if="kits.length" label="Saved">
            <option v-for="k in kits" :key="k.id" :value="k.id">{{ k.name }}</option>
          </optgroup>
        </select>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue'
import { useDrumDesigner } from '../composables/useDrumDesigner'
import { useDrumKitPatches, builtinKitOptions } from '../composables/useDrumKitPatches'
import { useCustomInstruments } from '../composables/useCustomInstruments'
import { useStyleCatalog } from '../composables/useStyleCatalog'
import { auditionDrumHit, disposeDrumPreview, startDrumGroove, stopDrumGroove } from '../soundfonts/audition'
import { type DrumKitPatch, type DrumOscWave, type DrumNoiseType, BUILTIN_KITS } from '../soundfonts/synthDrums'

const { open, close } = useDrumDesigner()

// The preset menu is every built-in kit (registry is the single source of truth).
const PRESETS: { id: string; label: string; patch: DrumKitPatch }[] =
  Object.entries(BUILTIN_KITS).map(([id, e]) => ({ id, label: e.label, patch: e.patch }))

const WAVES: DrumOscWave[] = ['sine', 'triangle', 'sawtooth', 'square']
const NOISES: DrumNoiseType[] = ['white', 'pink', 'brown']
// Kick/sub live in the sub-bass range — a chromatic run from A0 to C2 covers every
// built-in kit's note choice with headroom either side.
const NOTES = ['A0', 'A#0', 'B0', 'C1', 'C#1', 'D1', 'D#1', 'E1', 'F1', 'F#1', 'G1', 'G#1', 'A1', 'A#1', 'B1', 'C2']
const PADS: { label: string; pitch: number }[] = [
  { label: 'Kick', pitch: 36 }, { label: 'Snare', pitch: 38 }, { label: 'Clap', pitch: 39 },
  { label: 'Cl. Hat', pitch: 42 }, { label: 'Op. Hat', pitch: 46 }, { label: 'Crash', pitch: 49 },
  { label: 'Ride', pitch: 51 }, { label: 'Tom', pitch: 45 },
]

const clone = (p: DrumKitPatch): DrumKitPatch => JSON.parse(JSON.stringify(p))

const selectedPreset = ref(PRESETS[0].id)
const patch = ref<DrumKitPatch>(clone(PRESETS[0].patch))

// ── Library + assignment ──────────────────────────────────────────────────────
const { kits, saveKit, deleteKit, assignKit, getKit, assignedId } = useDrumKitPatches()
const { activeStyleId } = useStyleCatalog()

// Every built-in + saved kit, in one list — what ◀ ▶ pages through (the preset
// dropdown above only lists built-ins; this is the superset used for browsing/A-B).
const combined = computed(() => [
  ...PRESETS,
  ...kits.value.map(k => ({ id: k.id, label: k.name, patch: k.patch })),
])
const browseIndex = ref(0)

function loadPreset(id: string) {
  const found = PRESETS.find(p => p.id === id)
  if (found) { patch.value = clone(found.patch); browseIndex.value = combined.value.findIndex(e => e.id === id) }
}

/** Step to the previous/next entry in `combined` (built-ins then saved kits),
 *  wrapping around — the A/B tool for comparing a feel against the demo loop. */
function browse(delta: number) {
  const list = combined.value
  if (!list.length) return
  browseIndex.value = (browseIndex.value + delta + list.length) % list.length
  const entry = list[browseIndex.value]
  patch.value = clone(entry.patch)
  selectedPreset.value = entry.id   // only visibly reflected when it's a built-in
  saveName.value = entry.label
}

const secs = (s: number) => (s >= 1 ? `${s.toFixed(2)} s` : `${Math.round(s * 1000)} ms`)
const pct = (v: number) => `${Math.round(v * 100)}%`

function play(pitch: number) {
  void auditionDrumHit(patch.value, pitch)
}

// ── Groove loop ────────────────────────────────────────────────────────────────
const isLooping = ref(false)
const tempo = ref(96)

function toggleLoop() {
  if (isLooping.value) {
    stopDrumGroove()
    isLooping.value = false
  } else {
    void startDrumGroove(() => patch.value, tempo.value)
    isLooping.value = true
  }
}
// Changing tempo while the loop is running restarts it at the new rate (still reading
// the live patch getter, so a tempo change doesn't interrupt slider-edit hotness).
watch(tempo, (bpm) => { if (isLooping.value) void startDrumGroove(() => patch.value, bpm) })

const BUILTIN_OPTIONS = builtinKitOptions()

const saveName = ref('')
const scope = ref<'all' | 'style'>('all')

function doSave() {
  const saved = saveKit(saveName.value, patch.value)
  saveName.value = saved.name   // keep the name so a re-save updates in place
}
function loadSaved(id: string) {
  const s = getKit(id)
  if (s) { patch.value = clone(s.patch); saveName.value = s.name; browseIndex.value = combined.value.findIndex(e => e.id === id) }
}
function onAssign(id: string) {
  assignKit(id || null, scope.value === 'style' ? (activeStyleId.value ?? undefined) : undefined)
}
const currentAssign = computed(() => assignedId(activeStyleId.value ?? undefined, scope.value))

// ── Sample base (blend a real sample under the synth kit) ────────────────────────
const ci = useCustomInstruments()
const ciSupported = ci.supported()
const drumSampleKits = computed(() => ci.instruments.value.filter(i => i.kind === 'drums'))
// <select> works in plain strings; the patch field is undefined for "none".
const sampleKitIdModel = computed({
  get: () => patch.value.sampleKitId ?? '',
  set: (id: string) => { patch.value.sampleKitId = id || undefined },
})

watch(open, (v) => {
  if (v) { if (ciSupported) void ci.ensureLoaded() }
  else { disposeDrumPreview(); stopDrumGroove(); isLooping.value = false }
})
onUnmounted(() => { disposeDrumPreview(); stopDrumGroove() })
</script>

<style scoped>
.dd-overlay {
  position: fixed; inset: 0; z-index: 1000;
  background: rgba(0, 0, 0, 0.5);
  display: flex; align-items: center; justify-content: center; padding: 1rem;
}
.dd-modal {
  background: var(--surface); color: var(--text);
  border: 1px solid var(--border); border-radius: 10px;
  width: min(560px, 100%); max-height: 86vh; overflow: auto;
  padding: 1rem 1.25rem;
}
.dd-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.5rem; }
.dd-header h2 { margin: 0; font-size: 1.1rem; }
.dd-x { background: none; border: none; color: var(--text-faint); cursor: pointer; font-size: 1rem; }
.dd-x:hover { color: var(--text); }
section { border-top: 1px solid var(--border); padding-top: 0.85rem; margin-top: 0.85rem; }
.dd-first { border-top: none; padding-top: 0; margin-top: 0; }
h3 { font-size: 0.85rem; margin: 0 0 0.5rem; color: var(--text); }
.dd-hint { font-size: 0.78rem; color: var(--text-faint); margin: 0.5rem 0 0; line-height: 1.5; }
.dd-input {
  font: inherit; padding: 0.35rem 0.5rem; border: 1px solid var(--border);
  border-radius: 6px; background: var(--surface); color: var(--text);
}
.dd-head-row { display: flex; align-items: center; justify-content: space-between; gap: 0.6rem; }
.dd-preset { min-width: 200px; }
.dd-browse { display: flex; align-items: center; gap: 0.4rem; }
.dd-loop { display: flex; align-items: center; gap: 0.5rem; }
.dd-loop-btn { padding: 0.3rem 0.7rem; font-size: 0.78rem; }
.dd-loop-btn.is-on { background: #4caf50; }
.dd-tempo { width: 90px; accent-color: var(--accent); }
.dd-save-row { display: flex; gap: 0.5rem; align-items: center; margin-bottom: 0.5rem; }
.dd-save-row .dd-input { flex: 1; }
.dd-btn {
  font: inherit; padding: 0.4rem 0.9rem; border: 1px solid var(--border);
  border-radius: 6px; background: var(--accent); color: var(--accent-contrast, #fff); cursor: pointer;
}
.dd-btn:disabled { opacity: 0.5; cursor: default; }
.dd-list { list-style: none; margin: 0; padding: 0; }
.dd-item { display: flex; align-items: center; gap: 0.5rem; padding: 0.3rem 0; border-bottom: 1px solid var(--border); }
.dd-item-name { flex: 1; font-weight: 600; font-size: 0.85rem; }
.dd-mini {
  font-size: 0.72rem; background: none; border: 1px solid var(--border);
  border-radius: 5px; color: var(--text-faint); cursor: pointer; padding: 0.2rem 0.5rem;
}
.dd-mini:hover { color: var(--text); border-color: var(--accent); }
.dd-del { font-size: 0.72rem; background: none; border: 1px solid var(--border); border-radius: 5px; color: var(--text-faint); cursor: pointer; padding: 0.2rem 0.5rem; }
.dd-del:hover { color: #e66; border-color: #e66; }
.dd-scope { display: flex; gap: 0.7rem; font-size: 0.76rem; color: var(--text-faint); }
.dd-scope label { display: flex; align-items: center; gap: 0.25rem; cursor: pointer; }
.dd-row { display: grid; grid-template-columns: 90px 1fr 84px; align-items: center; gap: 0.6rem; margin-bottom: 0.45rem; }
.dd-label { font-size: 0.8rem; color: var(--text-faint); }
.dd-slider { width: 100%; accent-color: var(--accent); }
.dd-val { font-size: 0.76rem; color: var(--text-faint); text-align: right; font-variant-numeric: tabular-nums; }

.dd-pads { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.5rem; margin-top: 0.25rem; }
.dd-pad {
  cursor: pointer; font: inherit; font-size: 0.78rem; padding: 0.7rem 0.3rem;
  background: var(--surface); color: var(--text-faint);
  border: 1px solid var(--border); border-radius: 6px;
}
.dd-pad:active { background: var(--accent); color: var(--accent-contrast, #fff); }
</style>
