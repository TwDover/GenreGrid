<!--
  GenreGrid — a style-based MIDI generator.
  Copyright (C) 2026 Tw Dover

  This program is free software: you can redistribute it and/or modify it under
  the terms of the GNU General Public License v3 or (at your option) any later
  version. Distributed WITHOUT ANY WARRANTY. See <https://www.gnu.org/licenses/>.
-->
<template>
  <div class="editor-overlay" @click.self="$emit('close')">
    <div class="editor-modal">
      <div class="editor-header">
        <span class="editor-title">Style Editor</span>
        <span class="editor-base">Based on: {{ baseStyleName }}</span>
        <StyleRadar v-if="!loading && !error" :style="(draft as any)" :size="72" :editable="true" @update:style="onRadarDrag" />
        <button class="close-btn" @click="$emit('close')">✕</button>
      </div>

      <div v-if="loading" class="editor-loading">Loading…</div>
      <div v-else-if="error" class="editor-error">{{ error }}</div>
      <template v-else>
        <div class="editor-body">
          <div class="field-group">
            <span class="group-label">Identity</span>
            <div class="field-row">
              <label>Name</label>
              <input class="text-input" v-model="draft.name" placeholder="My Custom Style" maxlength="40" />
            </div>
            <div class="field-row">
              <label>ID <span class="hint">(a-z, 0-9, _)</span></label>
              <input class="text-input mono" v-model="draft.id" placeholder="my_style" maxlength="40" />
            </div>
          </div>

          <div class="field-group">
            <span class="group-label">Tempo</span>
            <div class="field-row">
              <label>BPM Min</label>
              <input type="number" class="num-input" v-model.number="draft.bpm_range[0]" min="40" max="240" />
            </div>
            <div class="field-row">
              <label>BPM Max</label>
              <input type="number" class="num-input" v-model.number="draft.bpm_range[1]" min="40" max="240" />
            </div>
          </div>

          <div class="field-group">
            <span class="group-label">Feel</span>
            <div class="field-row">
              <label>Velocity Base</label>
              <div class="slider-group">
                <input type="range" class="slider" min="40" max="110" step="1" v-model.number="draft.velocity_base" />
                <span class="slider-val">{{ draft.velocity_base }}</span>
              </div>
            </div>
            <div class="field-row">
              <label>Groove Push</label>
              <div class="slider-group">
                <input type="range" class="slider" min="-0.05" max="0.05" step="0.001" v-model.number="draft.groove_push" />
                <span class="slider-val">{{ draft.groove_push.toFixed(3) }}</span>
              </div>
            </div>
          </div>

          <div class="field-group">
            <span class="group-label">Drums</span>
            <div class="field-row">
              <label>Hat Density</label>
              <div class="slider-group">
                <input type="range" class="slider" min="0" max="1" step="0.01" v-model.number="draft.drums.hat_density" />
                <span class="slider-val">{{ pct(draft.drums.hat_density) }}</span>
              </div>
            </div>
            <div class="field-row">
              <label>Swing</label>
              <div class="slider-group">
                <input type="range" class="slider" min="0.5" max="0.75" step="0.01" v-model.number="draft.drums.swing" />
                <span class="slider-val">{{ draft.drums.swing.toFixed(2) }}</span>
              </div>
            </div>
            <div class="field-row">
              <label>Triplet Prob</label>
              <div class="slider-group">
                <input type="range" class="slider" min="0" max="1" step="0.01" v-model.number="draft.drums.triplet_probability" />
                <span class="slider-val">{{ pct(draft.drums.triplet_probability) }}</span>
              </div>
            </div>
          </div>

          <div class="field-group">
            <span class="group-label">Melody</span>
            <div class="field-row">
              <label>Density</label>
              <div class="slider-group">
                <input type="range" class="slider" min="0" max="1" step="0.01" v-model.number="draft.melody.density" />
                <span class="slider-val">{{ pct(draft.melody.density) }}</span>
              </div>
            </div>
            <div class="field-row">
              <label>Stepwise Motion</label>
              <div class="slider-group">
                <input type="range" class="slider" min="0" max="1" step="0.01" v-model.number="draft.melody.stepwise_motion" />
                <span class="slider-val">{{ pct(draft.melody.stepwise_motion) }}</span>
              </div>
            </div>
            <div class="field-row">
              <label>Rest Probability</label>
              <div class="slider-group">
                <input type="range" class="slider" min="0" max="1" step="0.01" v-model.number="draft.melody.rest_probability" />
                <span class="slider-val">{{ pct(draft.melody.rest_probability) }}</span>
              </div>
            </div>
          </div>

          <div class="field-group">
            <span class="group-label">Bass</span>
            <div class="field-row">
              <label>Pattern Density</label>
              <div class="slider-group">
                <input type="range" class="slider" min="0" max="1" step="0.01" v-model.number="draft.bass.pattern_density" />
                <span class="slider-val">{{ pct(draft.bass.pattern_density) }}</span>
              </div>
            </div>
            <div class="field-row">
              <label>Sustain Bias</label>
              <div class="slider-group">
                <input type="range" class="slider" min="0" max="1" step="0.01" v-model.number="draft.bass.sustain_bias" />
                <span class="slider-val">{{ pct(draft.bass.sustain_bias) }}</span>
              </div>
            </div>
          </div>

          <div class="field-group">
            <span class="group-label">Harmony</span>
            <div class="field-row">
              <label>7th Chord Prob</label>
              <div class="slider-group">
                <input type="range" class="slider" min="0" max="1" step="0.01" v-model.number="draft.chord_extensions.allow_7th" />
                <span class="slider-val">{{ pct(draft.chord_extensions.allow_7th) }}</span>
              </div>
            </div>
            <div class="field-row">
              <label>9th Chord Prob</label>
              <div class="slider-group">
                <input type="range" class="slider" min="0" max="1" step="0.01" v-model.number="draft.chord_extensions.allow_9th" />
                <span class="slider-val">{{ pct(draft.chord_extensions.allow_9th) }}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="editor-footer">
          <span v-if="saveError" class="save-error">{{ saveError }}</span>
          <button class="reset-btn" @click="resetDraft">Reset</button>
          <button class="save-btn" :disabled="saving" @click="handleSave">
            {{ saving ? 'Saving…' : 'Save Custom Style' }}
          </button>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { fetchStyleDetail, saveCustomStyle } from '../services/api'
import StyleRadar from './StyleRadar.vue'

const props = defineProps<{ styleId: string; baseStyleName: string }>()
const emit = defineEmits<{
  (e: 'close'): void
  (e: 'saved', styleId: string): void
}>()

const loading = ref(true)
const error = ref<string | null>(null)
const saving = ref(false)
const saveError = ref<string | null>(null)

interface Draft {
  id: string; name: string; bpm_range: [number, number]
  velocity_base: number; groove_push: number
  drums: { hat_density: number; swing: number; triplet_probability: number }
  melody: { density: number; stepwise_motion: number; rest_probability: number }
  bass: { pattern_density: number; sustain_bias: number }
  chord_extensions: { allow_7th: number; allow_9th: number }
}

const draft = ref<Draft>({
  id: '', name: '', bpm_range: [80, 140],
  velocity_base: 80, groove_push: 0,
  drums: { hat_density: 0.5, swing: 0.5, triplet_probability: 0.3 },
  melody: { density: 0.5, stepwise_motion: 0.6, rest_probability: 0.3 },
  bass: { pattern_density: 0.5, sustain_bias: 0.5 },
  chord_extensions: { allow_7th: 0.5, allow_9th: 0.3 },
})

let _source: Record<string, any> = {}

function applySource(data: Record<string, any>) {
  _source = data
  draft.value = {
    id: `custom_${data.id}`,
    name: `${data.name} (Custom)`,
    bpm_range: [...(data.bpm_range ?? [80, 140])] as [number, number],
    velocity_base: data.velocity_base ?? 80,
    groove_push: data.groove_push ?? 0,
    drums: {
      hat_density: data.drums?.hat_density ?? 0.5,
      swing: data.drums?.swing ?? 0.5,
      triplet_probability: data.drums?.triplet_probability ?? 0.3,
    },
    melody: {
      density: data.melody?.density ?? 0.5,
      stepwise_motion: data.melody?.stepwise_motion ?? 0.6,
      rest_probability: data.melody?.rest_probability ?? 0.3,
    },
    bass: {
      pattern_density: data.bass?.pattern_density ?? 0.5,
      sustain_bias: data.bass?.sustain_bias ?? 0.5,
    },
    chord_extensions: {
      allow_7th: data.chord_extensions?.allow_7th ?? 0.5,
      allow_9th: data.chord_extensions?.allow_9th ?? 0.3,
    },
  }
}

function resetDraft() { applySource(_source) }

async function load() {
  loading.value = true
  error.value = null
  try {
    const data = await fetchStyleDetail(props.styleId)
    applySource(data)
  } catch (e: any) {
    error.value = e.message ?? 'Failed to load style'
  } finally {
    loading.value = false
  }
}

watch(() => props.styleId, load, { immediate: true })

function pct(v: number) { return `${Math.round(v * 100)}%` }

function onRadarDrag(newStyle: Record<string, any>) {
  draft.value = {
    ...draft.value,
    groove_push: newStyle.groove_push ?? draft.value.groove_push,
    drums: { ...draft.value.drums, ...newStyle.drums },
    melody: { ...draft.value.melody, ...newStyle.melody },
    bass: { ...draft.value.bass, ...newStyle.bass },
    chord_extensions: { ...draft.value.chord_extensions, ...newStyle.chord_extensions },
  }
}

async function handleSave() {
  saveError.value = null
  const idClean = draft.value.id.replace(/[^a-z0-9_]/g, '_').slice(0, 40)
  if (!idClean) { saveError.value = 'ID is required'; return }
  if (!draft.value.name.trim()) { saveError.value = 'Name is required'; return }
  saving.value = true
  try {
    const payload = {
      ..._source,
      ...draft.value,
      id: idClean,
      drums: { ..._source.drums, ...draft.value.drums },
      melody: { ..._source.melody, ...draft.value.melody },
      bass: { ..._source.bass, ...draft.value.bass },
      chord_extensions: { ..._source.chord_extensions, ...draft.value.chord_extensions },
    }
    await saveCustomStyle(payload)
    emit('saved', idClean)
    emit('close')
  } catch (e: any) {
    saveError.value = e.message ?? 'Save failed'
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.editor-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 200;
}

.editor-modal {
  background: var(--panel);
  border: 1px solid color-mix(in srgb, var(--accent) 33%, transparent);
  border-radius: 12px;
  width: min(520px, 96vw);
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.editor-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.9rem 1.1rem;
  border-bottom: 1px solid var(--surface);
  flex-shrink: 0;
}

.editor-title {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text);
}

.editor-base {
  font-size: 0.72rem;
  color: var(--text-dim);
  flex: 1;
}

.close-btn {
  background: none;
  border: none;
  color: var(--text-dim);
  cursor: pointer;
  font-size: 0.9rem;
  line-height: 1;
  padding: 0.1rem 0.3rem;
}
.close-btn:hover { color: var(--text); }

.editor-loading, .editor-error {
  padding: 2rem;
  text-align: center;
  font-size: 0.8rem;
  color: var(--text-dim);
}
.editor-error { color: var(--error); }

.editor-body {
  overflow-y: auto;
  padding: 0.75rem 1.1rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
  flex: 1;
}

.field-group {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.group-label {
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--accent);
  margin-bottom: 0.1rem;
}

.field-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.field-row > label {
  font-size: 0.78rem;
  color: var(--text-dim);
  width: 130px;
  flex-shrink: 0;
}

.hint {
  font-size: 0.65rem;
  color: var(--text-faint);
}

.text-input {
  flex: 1;
  background: var(--panel-alt);
  border: 1px solid var(--surface);
  border-radius: 4px;
  color: var(--text);
  font-size: 0.8rem;
  padding: 0.25rem 0.5rem;
  outline: none;
}
.text-input:focus { border-color: color-mix(in srgb, var(--accent) 33%, transparent); }
.text-input.mono { font-family: monospace; }

.num-input {
  width: 70px;
  background: var(--panel-alt);
  border: 1px solid var(--surface);
  border-radius: 4px;
  color: var(--text);
  font-size: 0.8rem;
  padding: 0.25rem 0.4rem;
  outline: none;
  text-align: right;
}
.num-input:focus { border-color: color-mix(in srgb, var(--accent) 33%, transparent); }

.slider-group {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex: 1;
}

.slider {
  flex: 1;
  -webkit-appearance: none;
  appearance: none;
  height: 3px;
  background: var(--surface-hover);
  border-radius: 2px;
  outline: none;
  cursor: pointer;
}

.slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--accent);
  cursor: pointer;
}

.slider::-moz-range-thumb {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--accent);
  border: none;
  cursor: pointer;
}

.slider-val {
  font-size: 0.75rem;
  font-family: monospace;
  color: var(--accent);
  width: 42px;
  text-align: right;
  flex-shrink: 0;
}

.editor-footer {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 1.1rem;
  border-top: 1px solid var(--surface);
  flex-shrink: 0;
}

.save-error {
  font-size: 0.75rem;
  color: var(--error);
  flex: 1;
}

.reset-btn {
  font-size: 0.75rem;
  padding: 0.3rem 0.75rem;
  background: var(--surface);
  border: 1px solid var(--surface-hover);
  border-radius: 4px;
  color: var(--text-dim);
  cursor: pointer;
}
.reset-btn:hover { background: var(--surface-hover); color: var(--text); }

.save-btn {
  font-size: 0.78rem;
  padding: 0.35rem 1rem;
  background: var(--accent-surface-strong);
  border: 1px solid color-mix(in srgb, var(--accent) 27%, transparent);
  border-radius: 4px;
  color: var(--accent);
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.save-btn:hover:not(:disabled) { background: var(--accent-surface-strong); color: var(--accent-bright); }
.save-btn:disabled { opacity: 0.5; cursor: default; }
</style>
