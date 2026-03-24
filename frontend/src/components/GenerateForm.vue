<template>
  <form class="generate-form" @submit.prevent="$emit('submit', form)">
    <div class="style-field">
      <StyleSelector v-model="form.style_id" :styles="styles" />
      <div v-if="selectedStyle" class="style-info">
        <span>{{ selectedStyle.bpm_range[0] }}–{{ selectedStyle.bpm_range[1] }} BPM</span>
        <span class="dot">·</span>
        <span>{{ selectedStyle.default_scale }}</span>
      </div>
    </div>

    <div class="field-row">
      <div class="field">
        <label>
          BPM
          <span v-if="selectedStyle" class="hint">{{ selectedStyle.bpm_range[0] }}–{{ selectedStyle.bpm_range[1] }}</span>
        </label>
        <input
          type="number"
          v-model.number="form.bpm"
          :min="selectedStyle?.bpm_range[0] ?? 40"
          :max="selectedStyle?.bpm_range[1] ?? 240"
        />
      </div>
      <div class="field">
        <label>Bars</label>
        <input type="number" v-model.number="form.bars" min="1" max="32" />
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
        </select>
      </div>
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
    </div>
  </form>
</template>

<script setup lang="ts">
import { reactive, computed, watch } from 'vue'
import StyleSelector from './StyleSelector.vue'
import type { StyleInfo, GenerateRequest, GenerateResponse } from '../types/midi'

const props = defineProps<{
  styles: StyleInfo[]
  loading: boolean
  replayData?: GenerateResponse | null
}>()

defineEmits<{ (e: 'submit', form: GenerateRequest): void }>()

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
  parts: ['chords', 'bass', 'melody', 'drums'],
  seed: undefined,
})

const selectedStyle = computed(() => props.styles.find(s => s.id === form.style_id))

// Snap BPM to midpoint when style changes
watch(selectedStyle, (style) => {
  if (!style) return
  const [min, max] = style.bpm_range
  form.bpm = Math.round((min + max) / 2)
})

// Pre-fill form on replay
watch(() => props.replayData, (data) => {
  if (!data) return
  form.style_id = data.style
  form.key = data.summary.key_root
  form.scale = data.summary.scale
  form.bpm = data.summary.bpm
  form.bars = data.summary.bars
  form.seed = data.seed
})

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

.style-info {
  display: flex;
  gap: 0.4rem;
  align-items: center;
  font-size: 0.72rem;
  color: #55556a;
  padding-left: 0.1rem;
}

.dot { color: #3a3a54; }

.hint {
  font-size: 0.7rem;
  color: #55556a;
  margin-left: 0.4rem;
  font-weight: normal;
  text-transform: none;
  letter-spacing: 0;
}

.form-actions {
  display: flex;
  gap: 0.75rem;
  margin-top: 0.5rem;
}

.randomize-btn {
  background: #1a1a24;
  border: 1px solid #2a2a3e;
  color: #8888a0;
  padding: 0.75rem 1rem;
  border-radius: 8px;
  font-size: 0.9rem;
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s;
  white-space: nowrap;
}
.randomize-btn:hover:not(:disabled) {
  border-color: #a78bfa;
  color: #a78bfa;
}
.randomize-btn:disabled { opacity: 0.4; cursor: not-allowed; }
</style>
