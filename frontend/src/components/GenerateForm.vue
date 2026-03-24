<template>
  <form class="generate-form" @submit.prevent="$emit('submit', form)">
    <StyleSelector v-model="form.style_id" :styles="styles" />

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

    <div class="field-row">
      <div class="field">
        <label>BPM</label>
        <input type="number" v-model.number="form.bpm" min="40" max="240" />
      </div>
      <div class="field">
        <label>Bars</label>
        <input type="number" v-model.number="form.bars" min="1" max="32" />
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

    <button type="submit" :disabled="loading" class="generate-btn">
      {{ loading ? 'Generating...' : 'Generate' }}
    </button>
  </form>
</template>

<script setup lang="ts">
import { reactive } from 'vue'
import StyleSelector from './StyleSelector.vue'
import type { StyleInfo, GenerateRequest } from '../types/midi'

const props = defineProps<{
  styles: StyleInfo[]
  loading: boolean
}>()

defineEmits<{ (e: 'submit', form: GenerateRequest): void }>()

const keys = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
const allParts = ['chords', 'bass', 'melody', 'drums']

const form = reactive<GenerateRequest>({
  style_id: props.styles[0]?.id ?? 'dark_trap',
  key: 'C',
  scale: 'minor',
  bpm: 140,
  bars: 8,
  complexity: 0.5,
  variation: 0.4,
  parts: ['chords', 'bass', 'melody', 'drums'],
})
</script>
