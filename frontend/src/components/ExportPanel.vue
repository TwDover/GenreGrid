<!--
  GenreGrid — a style-based MIDI generator.
  Copyright (C) 2026 Tw Dover

  This program is free software: you can redistribute it and/or modify it under
  the terms of the GNU General Public License v3 or (at your option) any later
  version. Distributed WITHOUT ANY WARRANTY. See <https://www.gnu.org/licenses/>.
-->
<template>
  <div v-if="loading && !history.length" class="export-panel">
    <div class="skeleton-card">
      <div class="skeleton-row">
        <div class="skeleton-block" style="width:30%"></div>
        <div class="skeleton-block" style="width:45%"></div>
      </div>
      <div class="skeleton-row">
        <div class="skeleton-block" style="width:20%"></div>
        <div class="skeleton-block" style="width:55%"></div>
      </div>
    </div>
  </div>
  <div v-else-if="history.length" class="export-panel">
    <div v-if="loading" class="generating-banner">Generating…</div>
    <div class="history-header">
      <span class="history-title">Generations</span>
      <span class="history-count">{{ history.length }}</span>
      <input v-model="searchQuery" type="text" class="history-search" placeholder="Filter…" />
      <button class="arrange-toggle" :class="{ active: showArrange }" @click="showArrange = !showArrange" title="Open arrangement builder">
        {{ showArrange ? '▲ Arrange' : '▼ Arrange' }}
      </button>
    </div>
    <ArrangementBuilder v-if="showArrange" ref="arrangeRef" />
    <div class="history-list">
      <div
        v-for="response in filteredHistory"
        :key="response.generation_id"
        class="history-entry"
        :class="{ expanded: expandedId === response.generation_id }"
      >
        <button class="history-row" @click="toggle(response.generation_id)">
          <button
            class="star-btn"
            :class="{ starred: starredIds?.has(response.generation_id) }"
            @click.stop="emit('toggle-star', response.generation_id)"
            :title="starredIds?.has(response.generation_id) ? 'Unpin' : 'Pin — keeps this entry past the 10-item cap'"
          >{{ starredIds?.has(response.generation_id) ? '★' : '☆' }}</button>
          <span class="entry-style">{{ formatStyle(response.style) }}</span>
          <span
            class="entry-name"
            :class="{ 'has-name': !!genNames[response.generation_id] }"
            :contenteditable="editingName === response.generation_id ? 'true' : 'false'"
            @click.stop="startEditName(response.generation_id)"
            @blur="saveName(response.generation_id, $event)"
            @keydown.enter.prevent="($event.target as HTMLElement).blur()"
            :title="'Double-click to name this generation'"
          >{{ genNames[response.generation_id] ?? '' }}</span>
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
            <a
              v-if="response.summary.mode === 'arrangement'"
              class="seed-action"
              :href="sectionsUrl(response.generation_id)"
              download
              title="Download per-section stems as ZIP"
            >Sections ZIP</a>
            <button
              v-if="response.files.some(f => f.part === 'combined')"
              class="seed-action"
              @click.stop="addToArrange(response)"
              title="Add to arrangement builder"
            >+ Arrange</button>
            <template v-if="response.files.some(f => f.part === 'combined')">
              <div v-if="exportingId === response.generation_id" class="export-progress">
                {{ exportStem ? `${exportStem} ` : '' }}{{ Math.round(exportProgress * 100) }}%
              </div>
              <template v-else>
                <button
                  class="seed-action"
                  :disabled="isRendering || isRecording"
                  @click.stop="handleOfflineExport(response, 'wav')"
                  title="Offline render — full mix as WAV (fast)"
                >WAV ⚡</button>
                <button
                  class="seed-action"
                  :disabled="isRendering || isRecording"
                  @click.stop="handleOfflineExport(response, 'stems')"
                  title="Offline render — drums / bass / melodic as separate WAV files (fast)"
                >Stems ⚡</button>
              </template>
            </template>
          </div>
          <div v-if="response.progression?.length" class="progression-row">
            <span class="prog-label">Progression</span>
            <div class="prog-stack">
              <span class="prog-chords">{{ response.progression.join(' → ') }}</span>
              <span class="prog-resolved">
                {{ resolveProgression(response.progression, response.summary.key_root, response.summary.scale).join(' → ') }}
              </span>
            </div>
          </div>
          <div class="rating-row">
            <span class="rating-label">Rate</span>
            <button
              class="rate-btn"
              :class="{ active: ratings[response.generation_id] === 'up' }"
              @click.stop="rate(response.generation_id, 'up')"
              title="Good generation"
            >👍</button>
            <button
              class="rate-btn"
              :class="{ active: ratings[response.generation_id] === 'down' }"
              @click.stop="rate(response.generation_id, 'down')"
              title="Poor generation"
            >👎</button>
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
              :locked="lockedParts[response.generation_id]?.has(file.part) ?? false"
              :hasUndo="!!undoFiles[`${response.generation_id}:${file.part}`]"
              :keyRoot="response.summary.key_root"
              :scale="response.summary.scale"
              @regen="handleRegen(response, file.part)"
              @toggle-lock="toggleLock(response.generation_id, file.part)"
              @undo="handleUndo(response, file.part)"
            />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>


<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import PartCard from './PartCard.vue'
import QualityBadge from './QualityBadge.vue'
import ArrangementBuilder from './ArrangementBuilder.vue'
import type { GenerateResponse, FileInfo } from '../types/midi'
import { regeneratePart, saveToLibrary, bundleUrl, sectionsUrl } from '../services/api'
import { useMidiPlayer } from '../composables/useMidiPlayer'
import { resolveProgression } from '../utils/chordResolver'

const props = defineProps<{ history: GenerateResponse[]; loading?: boolean; starredIds?: Set<string> }>()
const emit = defineEmits<{
  (e: 'replay', response: GenerateResponse): void
  (e: 'part-regenned', genId: string, file: FileInfo): void
  (e: 'toggle-star', genId: string): void
}>()

const { isRecording, offlineRender, isRendering } = useMidiPlayer()
const showArrange = ref(false)
const arrangeRef = ref<InstanceType<typeof ArrangementBuilder> | null>(null)

// Search
const searchQuery = ref('')
const filteredHistory = computed(() => {
  const q = searchQuery.value.toLowerCase().trim()
  if (!q) return props.history
  return props.history.filter(r =>
    r.style.toLowerCase().includes(q) ||
    r.summary.key.toLowerCase().includes(q) ||
    (genNames.value[r.generation_id] ?? '').toLowerCase().includes(q)
  )
})

// Generation naming
const genNames = ref<Record<string, string>>({})
try {
  const saved = localStorage.getItem('genregrid_gen_names')
  if (saved) genNames.value = JSON.parse(saved)
} catch {}

const editingName = ref<string | null>(null)

function startEditName(genId: string) {
  editingName.value = genId
}

function saveName(genId: string, evt: Event) {
  const name = (evt.target as HTMLElement).textContent?.trim() ?? ''
  if (name) {
    genNames.value = { ...genNames.value, [genId]: name }
  } else {
    const { [genId]: _, ...rest } = genNames.value
    genNames.value = rest
  }
  editingName.value = null
  try { localStorage.setItem('genregrid_gen_names', JSON.stringify(genNames.value)) } catch {}
}

function addToArrange(response: GenerateResponse) {
  showArrange.value = true
  arrangeRef.value?.addGeneration(response)
}
const exportingId = ref<string | null>(null)
const exportProgress = ref(0)
const undoFiles = ref<Record<string, FileInfo>>({})

const ratings = ref<Record<string, 'up' | 'down'>>({})
try {
  const saved = localStorage.getItem('genregrid_ratings')
  if (saved) ratings.value = JSON.parse(saved)
} catch {}

function rate(genId: string, vote: 'up' | 'down') {
  if (ratings.value[genId] === vote) {
    const { [genId]: _, ...rest } = ratings.value
    ratings.value = rest
  } else {
    ratings.value = { ...ratings.value, [genId]: vote }
  }
  try { localStorage.setItem('genregrid_ratings', JSON.stringify(ratings.value)) } catch {}
}

const expandedId = ref<string | null>(null)
const lockedParts = ref<Record<string, Set<string>>>({})

function toggleLock(genId: string, part: string) {
  const cur = lockedParts.value[genId] ?? new Set<string>()
  const next = new Set(cur)
  if (next.has(part)) next.delete(part)
  else next.add(part)
  lockedParts.value = { ...lockedParts.value, [genId]: next }
}
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
  if (lockedParts.value[response.generation_id]?.has(part)) return
  const key = `${response.generation_id}:${part}`
  regenLoadingKey.value = key
  regenError.value = null
  try {
    const oldFile = response.files.find(f => f.part === part)
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
    if (oldFile) undoFiles.value = { ...undoFiles.value, [key]: oldFile }
    emit('part-regenned', response.generation_id, newFile)
  } catch (e: any) {
    regenError.value = e.message ?? 'Regeneration failed'
  } finally {
    regenLoadingKey.value = null
  }
}

function handleUndo(response: GenerateResponse, part: string) {
  const key = `${response.generation_id}:${part}`
  const old = undoFiles.value[key]
  if (!old) return
  const { [key]: _, ...rest } = undoFiles.value
  undoFiles.value = rest
  emit('part-regenned', response.generation_id, old)
}

const exportStem = ref<string | null>(null)

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

async function handleOfflineExport(response: GenerateResponse, mode: 'wav' | 'stems') {
  const combinedFile = response.files.find(f => f.part === 'combined')
  if (!combinedFile) return
  exportingId.value = response.generation_id
  exportProgress.value = 0
  exportStem.value = null
  const label = `${response.style}_${response.generation_id.slice(0, 8)}`
  const durationSeconds = response.summary.bars * (4 * 60 / response.summary.bpm)
  try {
    if (mode === 'wav') {
      const blob = await offlineRender(combinedFile.url, response.style, durationSeconds, 'all', v => { exportProgress.value = v })
      triggerDownload(blob, `${label}.wav`)
    } else {
      const stems = ['drums', 'bass', 'melodic'] as const
      for (let i = 0; i < stems.length; i++) {
        const stem = stems[i]
        exportStem.value = stem
        exportProgress.value = 0
        const blob = await offlineRender(combinedFile.url, response.style, durationSeconds, stem, v => {
          exportProgress.value = (i + v) / stems.length
        })
        triggerDownload(blob, `${label}_${stem}.wav`)
      }
    }
  } catch (e: any) {
    regenError.value = e.message ?? 'Export failed'
  } finally {
    exportingId.value = null
    exportProgress.value = 0
    exportStem.value = null
  }
}
</script>

<style scoped>
@keyframes shimmer {
  0%   { background-position: -400px 0; }
  100% { background-position: 400px 0; }
}

.skeleton-card {
  background: #060f14;
  border: 1px solid #0d2535;
  border-radius: 10px;
  padding: 0.75rem 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.skeleton-row {
  display: flex;
  gap: 0.75rem;
}

.skeleton-block {
  height: 0.75rem;
  border-radius: 4px;
  background: linear-gradient(90deg, #0d2535 25%, #122f40 50%, #0d2535 75%);
  background-size: 800px 100%;
  animation: shimmer 1.4s infinite linear;
}

.generating-banner {
  font-size: 0.72rem;
  color: #00c8ff;
  text-align: center;
  padding: 0.35rem;
  margin-bottom: 0.5rem;
  border: 1px solid #00c8ff33;
  border-radius: 6px;
  background: #001520;
  animation: shimmer 2s infinite linear;
  background-size: 800px 100%;
}

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

.history-search {
  flex: 1;
  max-width: 120px;
  background: #040a0e;
  border: 1px solid #0d2535;
  border-radius: 4px;
  color: #e0e0e8;
  font-size: 0.72rem;
  padding: 0.2rem 0.5rem;
  outline: none;
}
.history-search:focus { border-color: #00c8ff55; }
.history-search::placeholder { color: #2a4550; }

.entry-name {
  font-size: 0.7rem;
  color: #2a4550;
  cursor: text;
  padding: 0.05rem 0.25rem;
  border-radius: 3px;
  min-width: 20px;
  outline: none;
  border: 1px solid transparent;
  white-space: nowrap;
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
}
.entry-name.has-name { color: #4a7080; }
.entry-name:focus { border-color: #00c8ff44; background: #040a0e; color: #e0e0e8; }
.entry-name[contenteditable="true"] { cursor: text; }

.arrange-toggle {
  margin-left: auto;
  font-size: 0.68rem;
  padding: 0.2rem 0.6rem;
  background: #040a0e;
  border: 1px solid #0d2535;
  border-radius: 4px;
  color: #4a7080;
  cursor: pointer;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}
.arrange-toggle:hover { background: #081620; color: #e0e0e8; }
.arrange-toggle.active { border-color: #00c8ff44; color: #00c8ff; }

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
  min-height: 3rem;
  background: none;
  border: none;
  color: #e0e0e8;
  cursor: pointer;
  text-align: left;
}

.history-row:hover { background: #081620; }

.star-btn {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 1rem;
  color: #2a4550;
  padding: 0 0.1rem;
  line-height: 1;
  transition: color 0.15s, transform 0.1s;
  flex-shrink: 0;
}
.star-btn:hover { color: #f0c040; transform: scale(1.2); }
.star-btn.starred { color: #f0c040; }

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

.export-progress {
  font-size: 0.75rem;
  padding: 0.2rem 0.6rem;
  background: #001520;
  border: 1px solid #00c8ff44;
  border-radius: 4px;
  color: #00c8ff;
  font-family: monospace;
}

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

.prog-stack {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}

.prog-chords {
  font-family: monospace;
  font-size: 0.82rem;
  color: #7ae8ff;
  letter-spacing: 0.03em;
}

.prog-resolved {
  font-family: monospace;
  font-size: 0.72rem;
  color: #4a7080;
  letter-spacing: 0.02em;
}

.rating-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.3rem 0.75rem;
}

.rating-label {
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #2a4550;
}

.rate-btn {
  background: none;
  border: 1px solid transparent;
  border-radius: 4px;
  font-size: 0.85rem;
  cursor: pointer;
  padding: 0.1rem 0.35rem;
  opacity: 0.4;
  transition: opacity 0.15s, border-color 0.15s;
  line-height: 1;
}
.rate-btn:hover { opacity: 0.8; }
.rate-btn.active { opacity: 1; border-color: #00c8ff44; }
</style>
