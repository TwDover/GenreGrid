<!--
  GenreGrid — a style-based MIDI generator.
  Copyright (C) 2026 Tw Dover

  This program is free software: you can redistribute it and/or modify it under
  the terms of the GNU General Public License v3 or (at your option) any later
  version. Distributed WITHOUT ANY WARRANTY. See <https://www.gnu.org/licenses/>.
-->
<template>
  <form class="generate-form setup-form" @submit.prevent="emit('submit', form)">
    <StyleBrowser
      v-if="showBrowser"
      v-model="form.style_id"
      :styles="styles"
      @close="showBrowser = false"
    />
    <StyleEditor
      v-if="showEditor"
      :styleId="form.style_id"
      :baseStyleName="selectedStyle?.name ?? form.style_id"
      @close="showEditor = false"
      @saved="onStyleSaved"
    />

    <div class="setup-grid">
      <!-- ── Sound ──────────────────────────────────────────────────────── -->
      <section class="group">
        <span class="eyebrow">Sound</span>
        <div class="field">
          <label>Style</label>
          <div class="style-row">
            <select v-model="form.style_id" class="style-select">
              <option v-if="styles.length === 0" disabled value="">Loading…</option>
              <option v-for="s in styles" :key="s.id" :value="s.id">{{ s.name }}</option>
            </select>
            <button type="button" class="btn" @click="showBrowser = true" :disabled="styles.length === 0">Browse</button>
            <button type="button" class="btn" @click="showEditor = true" :disabled="!selectedStyle" title="Edit this style's parameters">Edit</button>
          </div>
          <div v-if="selectedStyle" class="style-info">
            <span>{{ selectedStyle.bpm_range[0] }}–{{ selectedStyle.bpm_range[1] }} BPM</span>
            <span class="dot">·</span>
            <span>{{ selectedStyle.default_scale }}</span>
            <span v-if="selectedStyle.custom" class="custom-badge">custom</span>
          </div>
        </div>

        <div class="field-row">
          <div class="field">
            <label>Key</label>
            <select v-model="form.key">
              <option v-for="k in keys" :key="k" :value="k">{{ k }}</option>
            </select>
          </div>
          <div class="field">
            <label>Scale</label>
            <select v-model="form.scale">
              <option value="major">Major</option>
              <option value="minor">Minor</option>
              <option value="dorian">Dorian</option>
              <option value="phrygian">Phrygian</option>
              <option value="mixolydian">Mixolydian</option>
              <option value="pentatonic_minor">Pentatonic Minor</option>
              <option value="pentatonic_major">Pentatonic Major</option>
              <option value="blues">Blues</option>
              <option value="harmonic_minor">Harmonic Minor</option>
              <option value="phrygian_dominant">Phrygian Dominant</option>
              <option value="whole_tone">Whole Tone</option>
            </select>
          </div>
        </div>
        <div class="scale-notes">
          <span v-for="note in scaleNotes" :key="note" class="scale-note">{{ note }}</span>
        </div>

        <div class="field">
          <label>BPM <span v-if="selectedStyle" class="hint">{{ selectedStyle.bpm_range[0] }}–{{ selectedStyle.bpm_range[1] }}</span></label>
          <div class="bpm-row">
            <input
              type="number"
              v-model.number="form.bpm"
              :min="selectedStyle?.bpm_range[0] ?? 40"
              :max="selectedStyle?.bpm_range[1] ?? 240"
            />
            <button type="button" class="btn" @click="handleTap">Tap</button>
          </div>
        </div>
      </section>

      <!-- ── Form ───────────────────────────────────────────────────────── -->
      <section class="group">
        <span class="eyebrow">Form</span>
        <div class="field">
          <label>Bars</label>
          <input type="number" v-model.number="form.bars" min="1" max="128" />
        </div>

        <div class="field">
          <label>Parts</label>
          <div class="part-toggles">
            <label v-for="part in allParts" :key="part" class="toggle">
              <input type="checkbox" :value="part" v-model="form.parts" />
              {{ part.replace('_', ' ') }}
            </label>
          </div>
        </div>

        <div class="field" v-if="form.mode === 'loop'">
          <label>Section <span class="hint">shapes density &amp; bar count</span></label>
          <div class="section-grid">
            <label
              v-for="(p, key) in SECTION_PROFILES"
              :key="key"
              class="section-card"
              :class="{ active: form.section_type === key }"
              :title="p.desc"
            >
              <input type="radio" :value="key" v-model="form.section_type" />
              <span class="section-label">{{ p.label }}</span>
              <span class="section-bars">{{ p.bars[0] }}–{{ p.bars[1] }}</span>
            </label>
            <label class="section-card" :class="{ active: !form.section_type }" title="No shaping — use sliders as-is">
              <input type="radio" :value="undefined" v-model="form.section_type" />
              <span class="section-label">Free</span>
              <span class="section-bars">any</span>
            </label>
          </div>
          <p v-if="sectionBarHint" class="section-bar-hint">
            {{ sectionBarHint }}
            <button type="button" class="btn btn-quiet hint-apply" @click="applySuggestedBars">Apply</button>
          </p>
        </div>
      </section>

      <!-- ── Feel ───────────────────────────────────────────────────────── -->
      <section class="group">
        <span class="eyebrow">Feel</span>
        <div class="field">
          <label>Complexity <span class="value">{{ form.complexity.toFixed(2) }}</span></label>
          <input type="range" v-model.number="form.complexity" min="0" max="1" step="0.01" />
        </div>
        <div class="field">
          <label>Variation <span class="value">{{ form.variation.toFixed(2) }}</span></label>
          <input type="range" v-model.number="form.variation" min="0" max="1" step="0.01" />
        </div>
        <div class="field">
          <label>Feel <span class="value">{{ feelLabel }}</span></label>
          <input type="range" v-model.number="form.humanize" min="0" max="1" step="0.01" />
        </div>
      </section>
    </div>

    <!-- ── Advanced ─────────────────────────────────────────────────────── -->
    <details class="advanced">
      <summary>Advanced — blending, custom harmony, seed, presets</summary>
      <div class="adv-grid">
        <section class="group">
          <div class="field">
            <label>Blend with <span class="hint">mix two styles</span></label>
            <select v-model="form.blend_style_id">
              <option :value="undefined">None</option>
              <option v-for="s in styles.filter(s => s.id !== form.style_id)" :key="s.id" :value="s.id">{{ s.name }}</option>
            </select>
          </div>
          <div class="field" v-if="form.blend_style_id">
            <label>Blend amount <span class="value">{{ Math.round(form.blend_amount * 100) }}%</span></label>
            <input type="range" v-model.number="form.blend_amount" min="0" max="1" step="0.01" />
          </div>
          <label class="prior-toggle" v-if="selectedStyle?.has_prior">
            <input type="checkbox" v-model="form.use_priors" />
            <span>Use my local MIDI corpus <span class="hint">overlays patterns mined from a corpus you provide; you're responsible for its license</span></span>
          </label>
        </section>

        <section class="group">
          <div class="field">
            <label>Progression <span class="hint">e.g. i VII III VI</span></label>
            <input
              type="text"
              v-model="customProgressionRaw"
              placeholder="leave blank for style defaults"
              class="progression-input"
              @blur="parseProgression"
            />
            <div v-if="progressionError" class="field-error">{{ progressionError }}</div>
          </div>
          <div class="field">
            <label>Seed <span class="hint">blank = random</span></label>
            <input type="number" v-model.number="form.seed" placeholder="e.g. 1234567890" min="0" />
          </div>
        </section>

        <section class="group">
          <div class="field">
            <label>Presets</label>
            <select v-model="selectedPreset" @change="loadPreset">
              <option value="">Load preset…</option>
              <option v-for="p in presets" :key="p.name" :value="p.name">{{ p.name }}</option>
            </select>
          </div>
          <div class="preset-actions">
            <button type="button" class="btn" @click="savePreset" :disabled="presets.length >= 10">Save current</button>
            <button type="button" class="btn preset-delete" @click="deletePreset" :disabled="!selectedPreset">Delete</button>
          </div>
        </section>
      </div>
    </details>

    <div class="form-actions">
      <button type="submit" :disabled="loading" class="btn-primary generate-btn">
        {{ loading ? 'Generating…' : 'Generate' }}
      </button>
      <button type="button" class="btn randomize-btn" @click="randomize" :disabled="styles.length === 0">
        ⟳ Randomize
      </button>
      <div class="batch-row">
        <button type="button" class="btn batch-btn" :disabled="loading" @click="emit('batch', form, batchCount)">
          Batch ×{{ batchCount }}
        </button>
        <input type="number" v-model.number="batchCount" min="2" max="10" class="batch-count" aria-label="Batch count" />
      </div>
    </div>
  </form>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue'

interface SectionProfile { label: string; bars: [number, number]; desc: string }
const SECTION_PROFILES: Record<string, SectionProfile> = {
  intro:             { label: 'Intro',             bars: [4,  8],  desc: 'Sparse, establishes groove — melody minimal' },
  verse:             { label: 'Verse',             bars: [8,  16], desc: 'Moderate density, repetitive groove' },
  pre_chorus:        { label: 'Pre-Chorus',        bars: [2,  4],  desc: 'Builds tension, energy rises' },
  chorus:            { label: 'Chorus',            bars: [4,  8],  desc: 'Peak energy, full density — the hook' },
  post_chorus:       { label: 'Post-Chorus',       bars: [2,  4],  desc: 'Short hooky follow-up after chorus' },
  bridge:            { label: 'Bridge',            bars: [4,  8],  desc: 'Contrasting harmony and rhythm' },
  instrumental_solo: { label: 'Solo',              bars: [4,  16], desc: 'Melody leads, backing simplified' },
  outro:             { label: 'Outro',             bars: [4,  16], desc: 'Winding down, decreasing energy' },
}

const CHROMATIC = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
const SCALE_INTERVALS: Record<string, number[]> = {
  major:             [0,2,4,5,7,9,11],
  minor:             [0,2,3,5,7,8,10],
  dorian:            [0,2,3,5,7,9,10],
  phrygian:          [0,1,3,5,7,8,10],
  lydian:            [0,2,4,6,7,9,11],
  mixolydian:        [0,2,4,5,7,9,10],
  locrian:           [0,1,3,5,6,8,10],
  pentatonic_minor:  [0,3,5,7,10],
  pentatonic_major:  [0,2,4,7,9],
  blues:             [0,3,5,6,7,10],
  harmonic_minor:    [0,2,3,5,7,8,11],
  phrygian_dominant: [0,1,4,5,7,8,10],
  whole_tone:        [0,2,4,6,8,10],
}
import StyleBrowser from './StyleBrowser.vue'
import StyleEditor from './StyleEditor.vue'
import type { StyleInfo, GenerateRequest, GenerateResponse } from '../types/midi'

const props = defineProps<{
  styles: StyleInfo[]
  loading: boolean
  replayData?: GenerateResponse | null
  forcedMode?: 'loop' | 'arrangement'
}>()

const emit = defineEmits<{
  (e: 'submit', form: GenerateRequest): void
  (e: 'batch', form: GenerateRequest, count: number): void
  (e: 'refresh-styles'): void
}>()

const keys = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
const allParts = ['chords', 'bass', 'melody', 'drums', 'arpeggio', 'pads', 'counter_melody']

const form = reactive<GenerateRequest>({
  style_id: props.styles[0]?.id ?? 'dark_trap',
  key: 'C',
  scale: 'minor',
  bpm: 140,
  bars: 8,
  complexity: 0.5,
  variation: 0.4,
  parts: JSON.parse(localStorage.getItem('genregrid_parts') ?? '["chords","bass","melody","drums"]'),
  mode: props.forcedMode ?? 'loop',
  seed: undefined,
  section_type: undefined,
  humanize: 0.5,
  custom_progression: undefined,
  blend_style_id: undefined,
  blend_amount: 0.5,
  use_priors: false,
})

const selectedStyle = computed(() => props.styles.find(s => s.id === form.style_id))

// When the parent drives the mode via the top tab, keep the form in sync.
watch(() => props.forcedMode, (m) => { if (m) form.mode = m }, { immediate: true })

// Selecting a style adopts its typical BPM (midpoint of its range) and its
// default scale — also on first load, so the initial BPM matches the style
// shown in the dropdown rather than the raw default.
// Replay and randomize set their own BPM (and, for replay, scale) together
// with the style; they mark the change source so the watcher (which flushes
// after their handler) doesn't overwrite the values they chose.
let styleChangeSource: 'replay' | 'randomize' | null = null
watch(selectedStyle, (style) => {
  if (!style) return
  const src = styleChangeSource
  styleChangeSource = null
  if (src === null) {
    const [min, max] = style.bpm_range
    form.bpm = Math.round((min + max) / 2)
  }
  if (src !== 'replay' && style.default_scale) form.scale = style.default_scale
}, { immediate: true })

// Pre-fill form on replay
watch(() => props.replayData, (data) => {
  if (!data) return
  if (data.style !== form.style_id) styleChangeSource = 'replay'
  form.style_id = data.style
  form.key = data.summary.key_root
  form.scale = data.summary.scale
  form.bpm = data.summary.bpm
  form.bars = data.summary.bars
  form.mode = data.summary.mode
  form.seed = data.seed
  form.section_type = data.summary.section_type
})

// When section type changes, show a bar-count suggestion if current bars are outside typical range
const sectionBarHint = computed(() => {
  const key = form.section_type
  if (!key) return null
  const profile = SECTION_PROFILES[key]
  if (!profile) return null
  const [min, max] = profile.bars
  if (form.bars >= min && form.bars <= max) return null
  const suggested = Math.round((min + max) / 2)
  return `${profile.label} typically uses ${min}–${max} bars (you have ${form.bars}). Suggest: ${suggested}`
})

function applySuggestedBars() {
  const key = form.section_type
  if (!key) return
  const profile = SECTION_PROFILES[key]
  if (!profile) return
  const [min, max] = profile.bars
  form.bars = Math.round((min + max) / 2)
}

// Persist parts selection to localStorage
watch(() => form.parts, (parts) => {
  localStorage.setItem('genregrid_parts', JSON.stringify(parts))
}, { deep: true })

const scaleNotes = computed(() => {
  const intervals = SCALE_INTERVALS[form.scale] ?? SCALE_INTERVALS.minor
  const rootIdx = CHROMATIC.indexOf(form.key)
  if (rootIdx === -1) return []
  return intervals.map(iv => CHROMATIC[(rootIdx + iv) % 12])
})

const showBrowser = ref(false)
const showEditor = ref(false)
const batchCount = ref(4)

function onStyleSaved(newStyleId: string) {
  emit('refresh-styles')
  form.style_id = newStyleId
}
const tapTimes = ref<number[]>([])
let tapResetTimer: ReturnType<typeof setTimeout> | null = null

function handleTap() {
  const now = Date.now()
  tapTimes.value = [...tapTimes.value, now]
  if (tapResetTimer) clearTimeout(tapResetTimer)
  tapResetTimer = setTimeout(() => { tapTimes.value = [] }, 3000)
  if (tapTimes.value.length >= 2) {
    const intervals = tapTimes.value.slice(1).map((t, i) => t - tapTimes.value[i])
    const avgMs = intervals.reduce((a, b) => a + b, 0) / intervals.length
    const bpm = Math.round(60000 / avgMs)
    const [min, max] = selectedStyle.value?.bpm_range ?? [40, 240]
    form.bpm = Math.max(min, Math.min(max, bpm))
  }
}

interface Preset { name: string; form: GenerateRequest }
const presets = ref<Preset[]>(JSON.parse(localStorage.getItem('genregrid_presets') ?? '[]'))
const selectedPreset = ref('')

function savePreset() {
  const name = prompt('Preset name:')
  if (!name) return
  const existing = presets.value.findIndex(p => p.name === name)
  const entry = { name, form: { ...form } }
  if (existing >= 0) {
    presets.value[existing] = entry
  } else {
    presets.value = [...presets.value, entry]
  }
  localStorage.setItem('genregrid_presets', JSON.stringify(presets.value))
  selectedPreset.value = name
}

function loadPreset() {
  const p = presets.value.find(p => p.name === selectedPreset.value)
  if (!p) return
  Object.assign(form, p.form)
}

function deletePreset() {
  if (!selectedPreset.value) return
  presets.value = presets.value.filter(p => p.name !== selectedPreset.value)
  localStorage.setItem('genregrid_presets', JSON.stringify(presets.value))
  selectedPreset.value = ''
}

const feelLabel = computed(() => {
  const v = form.humanize
  if (v <= 0.2) return 'Quantized'
  if (v <= 0.4) return 'Tight'
  if (v <= 0.6) return 'Natural'
  if (v <= 0.8) return 'Loose'
  return 'Raw'
})

const customProgressionRaw = ref('')
const progressionError = ref('')
const VALID_ROMAN = /^(b?VII|b?VI|b?V|b?IV|b?III|b?II|b?I|b?vii|b?vi|b?v|b?iv|b?iii|b?ii|b?i)(°|dim|aug|sus[24]?|maj7?|m7?|7)?$/i

function parseProgression() {
  const raw = customProgressionRaw.value.trim()
  if (!raw) {
    form.custom_progression = undefined
    progressionError.value = ''
    return
  }
  const tokens = raw.split(/[\s,]+/).filter(Boolean)
  const invalid = tokens.filter(t => !VALID_ROMAN.test(t))
  if (invalid.length) {
    progressionError.value = `Unrecognised: ${invalid.join(', ')}`
    return
  }
  form.custom_progression = tokens
  progressionError.value = ''
}

function randomize() {
  if (props.styles.length === 0) return
  const style = props.styles[Math.floor(Math.random() * props.styles.length)]
  const [min, max] = style.bpm_range
  if (style.id !== form.style_id) styleChangeSource = 'randomize'
  form.style_id = style.id
  form.key = keys[Math.floor(Math.random() * keys.length)]
  form.bpm = Math.round(min + Math.random() * (max - min))
  form.complexity = Math.round((0.2 + Math.random() * 0.6) * 100) / 100
  form.variation = Math.round((0.2 + Math.random() * 0.5) * 100) / 100
  form.seed = undefined
}
</script>

<style scoped>
.prior-toggle {
  display: flex;
  align-items: flex-start;
  gap: var(--s2);
  cursor: pointer;
  font-size: var(--t-meta);
  color: var(--ink-dim);
}
.prior-toggle input { width: auto; margin: 3px 0 0; accent-color: var(--accent); }

/* Style select + its Browse / Edit buttons on one aligned row — the select
 * flexes, the buttons stay their natural width, all the same height. */
.style-row { display: flex; gap: var(--s2); }
.style-select { flex: 1; min-width: 0; }
.style-row .btn { flex-shrink: 0; }

.style-info {
  display: flex;
  gap: var(--s2);
  align-items: center;
  font-size: var(--t-meta);
  color: var(--ink-faint);
}
.dot { color: var(--line); }

.custom-badge {
  font-size: var(--t-micro);
  background: var(--accent-wash);
  color: var(--accent);
  border: 1px solid var(--accent-edge);
  border-radius: var(--r-sm);
  padding: 0.05rem 0.35rem;
}

.progression-input { font-family: var(--f-mono); letter-spacing: 0.04em; }
.field-error { font-size: var(--t-meta); color: var(--bad); margin-top: var(--s1); }

/* Inline captions on labels — normal case, no uppercase inheritance. */
.hint {
  font-size: var(--t-meta);
  color: var(--ink-faint);
  margin-left: 0.4rem;
  font-weight: normal;
  text-transform: none;
  letter-spacing: 0;
}

.bpm-row { display: flex; gap: var(--s2); align-items: center; }
.bpm-row input { flex: 1; }
.bpm-row .btn { flex-shrink: 0; }

.scale-notes { display: flex; gap: var(--s1); flex-wrap: wrap; }
.scale-note {
  font-size: var(--t-meta);
  font-family: var(--f-mono);
  color: var(--accent);
  background: var(--accent-wash);
  border: 1px solid var(--accent-edge);
  border-radius: var(--r-sm);
  padding: 0.05rem 0.4rem;
}

/* Section profile grid — compact chips (label + bar range). */
.section-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(66px, 1fr)); gap: var(--s1); }
.section-card {
  display: flex; flex-direction: column; gap: 1px;
  padding: var(--s2);
  background: var(--ground);
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  cursor: pointer;
  transition: border-color 0.14s, background 0.14s;
}
.section-card input[type="radio"] { display: none; }
.section-card.active { border-color: var(--accent); background: var(--accent-wash); }
.section-card:hover:not(.active) { border-color: var(--ink-faint); }
.section-label { font-size: var(--t-meta); font-weight: 600; color: var(--ink); line-height: 1.15; }
.section-card.active .section-label { color: var(--accent); }
.section-bars { font-size: var(--t-micro); font-family: var(--f-mono); color: var(--ink-faint); }

.section-bar-hint {
  margin: var(--s1) 0 0;
  font-size: var(--t-meta);
  color: var(--warn);
  display: flex; align-items: center; gap: var(--s2);
}
.hint-apply {
  height: 26px; padding: 0 var(--s2);
  border: 1px solid color-mix(in srgb, var(--warn) 40%, var(--line));
  color: var(--warn);
}
.hint-apply:hover:not(:disabled) { background: var(--gold-surface); color: var(--warn); }

.preset-actions { display: flex; gap: var(--s2); }
.preset-actions .btn { flex: 1; }
.preset-delete:hover:not(:disabled) { border-color: var(--bad); color: var(--bad); }

/* Pinned to the bottom of the drawer so the actions stay reachable. One row:
 * Generate (widest) · Randomize · Batch — wrapping only on very narrow widths. */
.form-actions {
  position: sticky;
  bottom: 0;
  z-index: 3;
  display: flex;
  flex-wrap: wrap;
  gap: var(--s2);
  align-items: stretch;
  margin-top: var(--s4);
  /* Own the drawer's bottom spacing (sheet-body drops its bottom padding) so
   * the opaque fill pins flush to the scroll-area bottom — nothing shows
   * through beneath the buttons as you scroll. */
  padding: var(--s3) 0 var(--s5);
  background: var(--raised);
  box-shadow: 0 -10px 14px -2px var(--raised);
}
.form-actions .generate-btn { flex: 2 1 180px; height: 42px; font-size: var(--t-body); }
.randomize-btn { flex: 1 1 130px; height: 42px; }
.batch-row { display: flex; gap: var(--s1); flex-shrink: 0; }
.batch-row .batch-btn { height: 42px; }
.batch-count { width: 3rem; height: 42px; text-align: center; padding: 0 var(--s1); }
</style>
