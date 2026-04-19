<template>
  <div v-if="history.length" class="export-panel">
    <div class="history-header">
      <span class="history-title">Generations</span>
      <span class="history-count">{{ history.length }}</span>
    </div>
    <div class="history-list">
      <div
        v-for="response in history"
        :key="response.generation_id"
        class="history-entry"
        :class="{ expanded: expandedId === response.generation_id }"
      >
        <button class="history-row" @click="toggle(response.generation_id)">
          <span class="entry-style">{{ formatStyle(response.style) }}</span>
          <span class="entry-meta">
            <span v-if="response.summary.section_type" class="entry-section">{{ formatSection(response.summary.section_type) }}</span>
            {{ response.summary.key }} · {{ response.summary.bpm }} BPM · {{ response.summary.bars }} bars<span v-if="response._elapsed"> · {{ response._elapsed }}s</span>
          </span>
          <span class="entry-id">{{ response.generation_id }}</span>
          <span class="entry-chevron">{{ expandedId === response.generation_id ? '▲' : '▼' }}</span>
        </button>
        <div v-if="expandedId === response.generation_id" class="entry-body">
          <div class="seed-row">
            <span class="seed-label">Seed</span>
            <span class="seed-value">{{ response.seed }}</span>
            <button class="seed-action" @click.stop="copy(response.seed)" :title="'Copy seed'">
              {{ copied === response.seed ? '✓' : 'Copy' }}
            </button>
            <button class="seed-action replay" @click.stop="$emit('replay', response)" title="Load these settings into the form">
              Replay
            </button>
            <button
              v-if="response.quality"
              class="seed-action save"
              :class="{ saved: savedIds.has(response.generation_id) }"
              :disabled="savedIds.has(response.generation_id) || saveLoading === response.generation_id"
              @click.stop="handleSave(response)"
              title="Save to library to improve future generations"
            >
              {{ savedIds.has(response.generation_id) ? 'Saved' : saveLoading === response.generation_id ? '...' : 'Save' }}
            </button>
            <button class="seed-action" @click.stop="share(response)" title="Copy shareable link">
              {{ shared === response.generation_id ? '✓ Copied' : 'Share' }}
            </button>
            <a
              class="seed-action"
              :href="bundleUrl(response.generation_id)"
              download
              title="Download all parts as ZIP"
            >Download All</a>
          </div>
          <div v-if="response.progression?.length" class="progression-row">
            <span class="prog-label">Progression</span>
            <span class="prog-chords">{{ response.progression.join(' → ') }}</span>
          </div>
          <QualityBadge v-if="response.quality" :score="response.quality" />
          <div v-if="regenError" class="regen-error">{{ regenError }}</div>
          <div class="part-cards">
            <PartCard
              v-for="file in response.files"
              :key="file.url"
              :file="file"
              :styleId="response.style"
              :regenLoading="regenLoadingKey === `${response.generation_id}:${file.part}`"
              @regen="handleRegen(response, file.part)"
            />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import PartCard from './PartCard.vue'
import QualityBadge from './QualityBadge.vue'
import type { GenerateResponse, FileInfo } from '../types/midi'
import { regeneratePart, saveToLibrary, bundleUrl } from '../services/api'

const props = defineProps<{ history: GenerateResponse[] }>()
const emit = defineEmits<{
  (e: 'replay', response: GenerateResponse): void
  (e: 'part-regenned', genId: string, file: FileInfo): void
}>()

const expandedId = ref<string | null>(null)
const copied = ref<number | null>(null)
const shared = ref<string | null>(null)
const regenLoadingKey = ref<string | null>(null)
const regenError = ref<string | null>(null)
const savedIds = ref<Set<string>>(new Set())
const saveLoading = ref<string | null>(null)

watch(() => props.history[0], (newest) => {
  if (!newest) return
  expandedId.value = newest.generation_id
  if (newest.auto_saved) {
    savedIds.value = new Set([...savedIds.value, newest.generation_id])
  }
}, { immediate: true })

function toggle(id: string) {
  expandedId.value = expandedId.value === id ? null : id
}

function formatStyle(id: string): string {
  return id.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

const _SECTION_LABELS: Record<string, string> = {
  intro: 'Intro', verse: 'Verse', pre_chorus: 'Pre-Ch', chorus: 'Chorus',
  post_chorus: 'Post-Ch', bridge: 'Bridge', instrumental_solo: 'Solo', outro: 'Outro',
}
function formatSection(id: string): string {
  return _SECTION_LABELS[id] ?? id
}

function copy(seed: number) {
  navigator.clipboard.writeText(String(seed))
  copied.value = seed
  setTimeout(() => { copied.value = null }, 2000)
}

function share(response: GenerateResponse) {
  navigator.clipboard.writeText(window.location.href)
  shared.value = response.generation_id
  setTimeout(() => { shared.value = null }, 2000)
}

async function handleSave(response: GenerateResponse) {
  saveLoading.value = response.generation_id
  try {
    await saveToLibrary(response)
    savedIds.value = new Set([...savedIds.value, response.generation_id])
  } catch {
    // silently ignore — save is best-effort
  } finally {
    saveLoading.value = null
  }
}

async function handleRegen(response: GenerateResponse, part: string) {
  const key = `${response.generation_id}:${part}`
  regenLoadingKey.value = key
  regenError.value = null
  try {
    const newFile = await regeneratePart({
      generation_id: response.generation_id,
      part,
      style_id: response.style,
      key: response.summary.key_root,
      scale: response.summary.scale,
      bpm: response.summary.bpm,
      bars: response.summary.bars,
      complexity: response.summary.complexity,
      variation: response.summary.variation,
      mode: response.summary.mode,
      seed: response.seed,
    })
    emit('part-regenned', response.generation_id, newFile)
  } catch (e: any) {
    regenError.value = e.message ?? 'Regeneration failed'
  } finally {
    regenLoadingKey.value = null
  }
}
</script>

<style scoped>
.history-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}

.history-title {
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #4a7080;
}

.history-count {
  font-size: 0.7rem;
  background: #0d2535;
  color: #4a7080;
  border-radius: 10px;
  padding: 0.1rem 0.5rem;
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.history-entry {
  background: #060f14;
  border: 1px solid #0d2535;
  border-radius: 10px;
  overflow: hidden;
  transition: border-color 0.15s;
}

.history-entry.expanded {
  border-color: #00c8ff;
}

.history-row {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 1rem;
  background: none;
  border: none;
  color: #e0e0e8;
  cursor: pointer;
  text-align: left;
}

.history-row:hover { background: #081620; }

.entry-style {
  font-weight: 600;
  font-size: 0.9rem;
  min-width: 100px;
}

.entry-meta {
  font-size: 0.8rem;
  color: #4a7080;
  flex: 1;
  display: flex;
  align-items: center;
  gap: 0.4rem;
  flex-wrap: wrap;
}

.entry-section {
  font-size: 0.65rem;
  font-weight: 600;
  color: #00c8ff;
  background: #001520;
  border: 1px solid #00c8ff44;
  border-radius: 3px;
  padding: 0.05rem 0.4rem;
  white-space: nowrap;
}

.entry-id {
  font-size: 0.72rem;
  font-family: monospace;
  color: #2a4550;
}

.entry-chevron {
  font-size: 0.65rem;
  color: #2a4550;
}

.entry-body {
  padding: 0 1rem 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.seed-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  background: #040a0e;
  border-radius: 6px;
  border: 1px solid #0d2535;
}

.seed-label {
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #2a4550;
}

.seed-value {
  font-family: monospace;
  font-size: 0.82rem;
  color: #00c8ff;
  flex: 1;
}

.seed-action {
  font-size: 0.75rem;
  padding: 0.2rem 0.6rem;
  background: #0d2535;
  border: 1px solid #122f40;
  border-radius: 4px;
  color: #4a7080;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.seed-action:hover { background: #122f40; color: #e0e0e8; }

.seed-action.replay {
  color: #00c8ff;
  border-color: #00c8ff44;
}

.seed-action.replay:hover { background: #003450; color: #7ae8ff; }

.seed-action.save {
  color: #34d399;
  border-color: #34d39944;
}

.seed-action.save:hover:not(:disabled) { background: #064e3b; color: #6ee7b7; }

.seed-action.save.saved {
  color: #2a4550;
  border-color: #0d2535;
  cursor: default;
}

.seed-action:disabled { opacity: 0.6; cursor: default; }

.regen-error {
  font-size: 0.75rem;
  color: #f87171;
  padding: 0.3rem 0.5rem;
  background: #2a1010;
  border-radius: 4px;
}

.part-cards {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.progression-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.4rem 0.75rem;
  background: #040a0e;
  border-radius: 6px;
  border: 1px solid #0d2535;
}

.prog-label {
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #2a4550;
  flex-shrink: 0;
}

.prog-chords {
  font-family: monospace;
  font-size: 0.82rem;
  color: #7ae8ff;
  letter-spacing: 0.03em;
}
</style>
