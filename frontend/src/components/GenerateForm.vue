<template>
  <form class="generate-form" @submit.prevent="emit('submit', form)">
    <div class="style-field">
      <div class="style-selector-row">
        <StyleSelector v-model="form.style_id" :styles="styles" />
        <button type="button" class="browse-btn" @click="showBrowser = true" :disabled="styles.length === 0">Browse</button>
        <button type="button" class="edit-style-btn" @click="showEditor = true" :disabled="!selectedStyle" title="Edit this style's parameters">Edit</button>
      </div>
      <div v-if="selectedStyle" class="style-info">
        <span>{{ selectedStyle.bpm_range[0] }}–{{ selectedStyle.bpm_range[1] }} BPM</span>
        <span class="dot">·</span>
        <span>{{ selectedStyle.default_scale }}</span>
        <span v-if="selectedStyle.custom" class="custom-badge">custom</span>
        <div class="style-dna">
          <StyleRadar v-if="styleDetail" :style="styleDetail" :size="64" />
          <span class="dna-label">DNA</span>
        </div>
      </div>
    </div>

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

    <div class="field-row">
      <div class="field">
        <label>
          BPM
          <span v-if="selectedStyle" class="hint">{{ selectedStyle.bpm_range[0] }}–{{ selectedStyle.bpm_range[1] }}</span>
        </label>
        <div class="bpm-row">
          <input
            type="number"
            v-model.number="form.bpm"
            :min="selectedStyle?.bpm_range[0] ?? 40"
            :max="selectedStyle?.bpm_range[1] ?? 240"
          />
          <button type="button" class="tap-btn" @click="handleTap">Tap</button>
        </div>
      </div>
      <div class="field">
        <label>Bars</label>
        <input type="number" v-model.number="form.bars" min="1" max="128" />
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
      <label>Complexity <span class="value">{{ form.complexity.toFixed(2) }}</span></label>
      <input type="range" v-model.number="form.complexity" min="0" max="1" step="0.01" />
    </div>

    <div class="field">
      <label>Variation <span class="value">{{ form.variation.toFixed(2) }}</span></label>
      <input type="range" v-model.number="form.variation" min="0" max="1" step="0.01" />
    </div>

    <div class="field">
      <label>Parts</label>
      <div class="part-toggles">
        <label v-for="part in allParts" :key="part" class="toggle">
          <input type="checkbox" :value="part" v-model="form.parts" />
          {{ part }}
        </label>
      </div>
    </div>

    <div class="field">
      <label>Mode</label>
      <div class="mode-toggles">
        <label class="mode-option" :class="{ active: form.mode === 'loop' }">
          <input type="radio" value="loop" v-model="form.mode" />
          Loop
          <span class="mode-hint">all parts · all bars · uniform</span>
        </label>
        <label class="mode-option" :class="{ active: form.mode === 'arrangement' }">
          <input type="radio" value="arrangement" v-model="form.mode" />
          Arrangement
          <span class="mode-hint">intro · verse · chorus · outro</span>
        </label>
      </div>
    </div>

    <div class="field">
      <label>
        Section
        <span class="hint">shapes complexity, dynamics, and bar count</span>
      </label>
      <div class="section-grid">
        <label
          v-for="(p, key) in SECTION_PROFILES"
          :key="key"
          class="section-card"
          :class="{ active: form.section_type === key }"
        >
          <input type="radio" :value="key" v-model="form.section_type" />
          <span class="section-label">{{ p.label }}</span>
          <span class="section-bars">{{ p.bars[0] }}–{{ p.bars[1] }} bars</span>
          <span class="section-desc">{{ p.desc }}</span>
        </label>
        <label class="section-card" :class="{ active: !form.section_type }">
          <input type="radio" :value="undefined" v-model="form.section_type" />
          <span class="section-label">Free</span>
          <span class="section-bars">any</span>
          <span class="section-desc">No shaping — use sliders as-is</span>
        </label>
      </div>
      <p v-if="sectionBarHint" class="section-bar-hint">
        {{ sectionBarHint }}
        <button type="button" class="hint-apply" @click="applySuggestedBars">Apply</button>
      </p>
    </div>

    <div class="field">
      <label>Blend with <span class="hint">optional — mix two styles together</span></label>
      <div class="blend-row">
        <select v-model="form.blend_style_id" class="blend-select">
          <option :value="undefined">None</option>
          <option v-for="s in styles.filter(s => s.id !== form.style_id)" :key="s.id" :value="s.id">{{ s.name }}</option>
        </select>
        <input
          v-if="form.blend_style_id"
          type="range"
          v-model.number="form.blend_amount"
          min="0" max="1" step="0.01"
          class="blend-slider"
          :title="`Blend: ${Math.round(form.blend_amount * 100)}% ${styles.find(s => s.id === form.blend_style_id)?.name ?? ''}`"
        />
        <span v-if="form.blend_style_id" class="blend-pct">{{ Math.round(form.blend_amount * 100) }}%</span>
      </div>
    </div>

    <div class="field">
      <label>Feel <span class="value">{{ feelLabel }}</span></label>
      <input type="range" v-model.number="form.humanize" min="0" max="1" step="0.01" />
    </div>

    <div class="field">
      <label>
        Progression
        <span class="hint">optional — e.g. i VII III VI</span>
      </label>
      <input
        type="text"
        v-model="customProgressionRaw"
        placeholder="i VII III VI (leave blank to use style defaults)"
        class="progression-input"
        @blur="parseProgression"
      />
      <div v-if="progressionError" class="field-error">{{ progressionError }}</div>
    </div>

    <div class="field">
      <label>Seed <span class="hint">optional — leave blank for random</span></label>
      <input type="number" v-model.number="form.seed" placeholder="e.g. 1234567890" min="0" />
    </div>

    <div class="form-actions">
      <button type="button" class="randomize-btn" @click="randomize" :disabled="styles.length === 0">
        ⟳ Randomize
      </button>
      <button type="submit" :disabled="loading" class="generate-btn">
        {{ loading ? 'Generating...' : 'Generate' }}
      </button>
      <div class="batch-row">
        <button type="button" class="batch-btn" :disabled="loading" @click="emit('batch', form, batchCount)">
          Batch ×{{ batchCount }}
        </button>
        <input type="number" v-model.number="batchCount" min="2" max="10" class="batch-count" />
      </div>
    </div>

    <div class="preset-row">
      <select v-model="selectedPreset" class="preset-select" @change="loadPreset">
        <option value="">Load preset…</option>
        <option v-for="p in presets" :key="p.name" :value="p.name">{{ p.name }}</option>
      </select>
      <button type="button" class="preset-btn" @click="savePreset" :disabled="presets.length >= 10">Save</button>
      <button type="button" class="preset-btn preset-delete" @click="deletePreset" :disabled="!selectedPreset">Delete</button>
    </div>
  </form>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, shallowRef } from 'vue'

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
import StyleSelector from './StyleSelector.vue'
import StyleBrowser from './StyleBrowser.vue'
import StyleEditor from './StyleEditor.vue'
import StyleRadar from './StyleRadar.vue'
import { fetchStyleDetail } from '../services/api'
import type { StyleInfo, GenerateRequest, GenerateResponse } from '../types/midi'

const props = defineProps<{
  styles: StyleInfo[]
  loading: boolean
  replayData?: GenerateResponse | null
}>()

const emit = defineEmits<{
  (e: 'submit', form: GenerateRequest): void
  (e: 'batch', form: GenerateRequest, count: number): void
  (e: 'refresh-styles'): void
}>()

const keys = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
const allParts = ['chords', 'bass', 'melody', 'drums', 'arpeggio']

const form = reactive<GenerateRequest>({
  style_id: props.styles[0]?.id ?? 'dark_trap',
  key: 'C',
  scale: 'minor',
  bpm: 140,
  bars: 8,
  complexity: 0.5,
  variation: 0.4,
  parts: JSON.parse(localStorage.getItem('genregrid_parts') ?? '["chords","bass","melody","drums"]'),
  mode: 'loop',
  seed: undefined,
  section_type: undefined,
  humanize: 0.5,
  custom_progression: undefined,
  blend_style_id: undefined,
  blend_amount: 0.5,
})

const selectedStyle = computed(() => props.styles.find(s => s.id === form.style_id))

// Clamp BPM and set default scale when style changes
watch(selectedStyle, (style) => {
  if (!style) return
  const [min, max] = style.bpm_range
  if (form.bpm < min || form.bpm > max) {
    form.bpm = Math.round((min + max) / 2)
  }
  if (style.default_scale) form.scale = style.default_scale
})

// Pre-fill form on replay
watch(() => props.replayData, (data) => {
  if (!data) return
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
const styleDetail = shallowRef<Record<string, any> | null>(null)

watch(() => form.style_id, async (id) => {
  styleDetail.value = null
  if (!id) return
  try { styleDetail.value = await fetchStyleDetail(id) } catch { /* radar just won't show */ }
}, { immediate: true })
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
  form.style_id = style.id
  form.key = keys[Math.floor(Math.random() * keys.length)]
  form.bpm = Math.round(min + Math.random() * (max - min))
  form.complexity = Math.round((0.2 + Math.random() * 0.6) * 100) / 100
  form.variation = Math.round((0.2 + Math.random() * 0.5) * 100) / 100
  form.seed = undefined
}
</script>

<style scoped>
.style-field {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.style-selector-row {
  display: flex;
  gap: 0.4rem;
}

.browse-btn {
  font-size: 0.75rem;
  padding: 0 0.75rem;
  background: #0d2535;
  border: 1px solid #122f40;
  border-radius: 6px;
  color: #4a7080;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.15s, color 0.15s;
  flex-shrink: 0;
}
.browse-btn:hover { background: #122f40; color: #e0e0e8; }

.edit-style-btn {
  font-size: 0.75rem;
  padding: 0 0.65rem;
  background: #0d2535;
  border: 1px solid #122f40;
  border-radius: 6px;
  color: #4a7080;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.15s, color 0.15s;
  flex-shrink: 0;
}
.edit-style-btn:hover:not(:disabled) { background: #003450; border-color: #00c8ff44; color: #00c8ff; }
.edit-style-btn:disabled { opacity: 0.4; cursor: not-allowed; }

.style-info {
  display: flex;
  gap: 0.4rem;
  align-items: center;
  font-size: 0.72rem;
  color: #2a4550;
  padding-left: 0.1rem;
}

.dot { color: #122f40; }

.custom-badge {
  font-size: 0.6rem;
  background: #003450;
  color: #00c8ff;
  border: 1px solid #00c8ff44;
  border-radius: 3px;
  padding: 0.05rem 0.35rem;
}

.style-dna {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 0.3rem;
}

.dna-label {
  font-size: 0.6rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #2a4550;
}

.blend-row {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}

.blend-select {
  flex: 1;
  min-width: 0;
}

.blend-slider {
  flex: 1;
  min-width: 0;
}

.blend-pct {
  font-size: 0.72rem;
  color: #4a7080;
  font-family: monospace;
  width: 2.5rem;
  text-align: right;
  flex-shrink: 0;
}

.progression-input {
  font-family: monospace;
  letter-spacing: 0.04em;
}

.field-error {
  font-size: 0.7rem;
  color: #ff6060;
  margin-top: 0.25rem;
}

.hint {
  font-size: 0.7rem;
  color: #2a4550;
  margin-left: 0.4rem;
  font-weight: normal;
  text-transform: none;
  letter-spacing: 0;
}

.form-actions {
  display: flex;
  gap: 0.75rem;
  margin-top: 0.5rem;
  flex-wrap: wrap;
}

.batch-row {
  display: flex;
  gap: 0.3rem;
  align-items: stretch;
}

.batch-btn {
  background: #060f14;
  border: 1px solid #0d2535;
  color: #4a7080;
  padding: 0.75rem 0.85rem;
  border-radius: 8px;
  font-size: 0.85rem;
  cursor: pointer;
  white-space: nowrap;
  transition: border-color 0.15s, color 0.15s;
}
.batch-btn:hover:not(:disabled) { border-color: #00c8ff44; color: #7ae8ff; }
.batch-btn:disabled { opacity: 0.4; cursor: not-allowed; }

.batch-count {
  width: 3rem;
  background: #040a0e;
  border: 1px solid #0d2535;
  border-radius: 6px;
  color: #4a7080;
  font-size: 0.85rem;
  text-align: center;
  padding: 0 0.4rem;
}

.randomize-btn {
  background: #060f14;
  border: 1px solid #0d2535;
  color: #4a7080;
  padding: 0.75rem 1rem;
  border-radius: 8px;
  font-size: 0.9rem;
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s;
  white-space: nowrap;
}
.randomize-btn:hover:not(:disabled) {
  border-color: #00c8ff;
  color: #00c8ff;
}
.randomize-btn:disabled { opacity: 0.4; cursor: not-allowed; }

.mode-toggles {
  display: flex;
  gap: 0.5rem;
}

.mode-option {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  padding: 0.5rem 0.75rem;
  background: #060f14;
  border: 1px solid #0d2535;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.85rem;
  color: #4a7080;
  transition: border-color 0.15s, color 0.15s;
}

.mode-option input[type="radio"] {
  display: none;
}

.mode-option.active {
  border-color: #00c8ff;
  color: #e0e0e8;
}

.mode-option:hover:not(.active) {
  border-color: #122f40;
  color: #b0d8e8;
}

.mode-hint {
  font-size: 0.68rem;
  color: #2a4550;
  font-weight: normal;
  text-transform: none;
  letter-spacing: 0;
}

.mode-option.active .mode-hint {
  color: #4a7080;
}

.bpm-row { display: flex; gap: 0.5rem; align-items: center; }
.bpm-row input { flex: 1; }
.tap-btn {
  font-size: 0.78rem;
  padding: 0.5rem 0.65rem;
  background: #060f14;
  border: 1px solid #0d2535;
  border-radius: 6px;
  color: #4a7080;
  cursor: pointer;
  white-space: nowrap;
  transition: border-color 0.15s, color 0.15s;
  flex-shrink: 0;
}
.tap-btn:hover { border-color: #00c8ff; color: #00c8ff; }

.preset-row {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  margin-top: -0.25rem;
}
.preset-select {
  flex: 1;
  background: #060f14;
  border: 1px solid #0d2535;
  border-radius: 6px;
  color: #4a7080;
  font-size: 0.8rem;
  padding: 0.35rem 0.5rem;
  cursor: pointer;
}
.preset-select:focus { outline: none; border-color: #00c8ff; }
.preset-btn {
  font-size: 0.75rem;
  padding: 0.35rem 0.65rem;
  background: #060f14;
  border: 1px solid #0d2535;
  border-radius: 6px;
  color: #4a7080;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.15s, color 0.15s;
}
.preset-btn:hover:not(:disabled) { border-color: #00c8ff; color: #00c8ff; }
.preset-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.preset-delete:hover:not(:disabled) { border-color: #f87171 !important; color: #f87171 !important; }

@media (max-width: 400px) {
  .field-row { grid-template-columns: 1fr; }
}

.scale-notes {
  display: flex;
  gap: 0.3rem;
  flex-wrap: wrap;
  padding: 0.1rem 0;
}
.scale-note {
  font-size: 0.7rem;
  font-family: monospace;
  color: #00c8ff;
  background: #060f14;
  border: 1px solid #0d2535;
  border-radius: 3px;
  padding: 0.1rem 0.35rem;
}

/* Section type grid */
.section-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 0.4rem;
}

.section-card {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
  padding: 0.45rem 0.55rem;
  background: #060f14;
  border: 1px solid #0d2535;
  border-radius: 6px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}

.section-card input[type="radio"] { display: none; }

.section-card.active {
  border-color: #00c8ff;
  background: #001520;
}

.section-card:hover:not(.active) {
  border-color: #122f40;
}

.section-label {
  font-size: 0.78rem;
  font-weight: 600;
  color: #b0d8e8;
  line-height: 1.2;
}

.section-card.active .section-label { color: #e0f0ff; }

.section-bars {
  font-size: 0.65rem;
  font-family: monospace;
  color: #00c8ff;
}

.section-card:not(.active) .section-bars { color: #2a4550; }

.section-desc {
  font-size: 0.62rem;
  color: #2a4550;
  line-height: 1.3;
  margin-top: 0.05rem;
}

.section-card.active .section-desc { color: #3a6070; }

.section-bar-hint {
  margin: 0.35rem 0 0;
  font-size: 0.72rem;
  color: #fbbf24;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.hint-apply {
  font-size: 0.68rem;
  padding: 0.15rem 0.5rem;
  background: #0d2535;
  border: 1px solid #fbbf2466;
  border-radius: 4px;
  color: #fbbf24;
  cursor: pointer;
  white-space: nowrap;
}

.hint-apply:hover { background: #3a2e10; }

@media (max-width: 480px) {
  .section-grid { grid-template-columns: repeat(2, 1fr); }
}
</style>
