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
      <button class="clear-btn" @click="emit('clear')" title="Clear unpinned generations">Clear</button>
    </div>
    <ArrangementBuilder v-if="showArrange" ref="arrangeRef" />
    <div class="history-list">
      <div
        v-for="response in filteredHistory"
        :key="response.generation_id"
        class="history-entry"
        :class="{ expanded: expandedId === response.generation_id }"
      >
        <div class="history-row" role="button" tabindex="0" @click="toggle(response.generation_id)" @keydown.enter="toggle(response.generation_id)">
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
          <button class="entry-del" @click.stop="emit('delete', response.generation_id)" title="Delete this generation">✕</button>
        </div>
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
            <button
              class="seed-action"
              :disabled="zipLoading === `${response.generation_id}:bundle`"
              @click.stop="handleZipDownload(response, 'bundle')"
              title="Download all parts as ZIP"
            >{{ zipLoading === `${response.generation_id}:bundle` ? '…' : 'Download All' }}</button>
            <button
              v-if="response.summary.mode === 'arrangement'"
              class="seed-action"
              :disabled="zipLoading === `${response.generation_id}:sections`"
              @click.stop="handleZipDownload(response, 'sections')"
              title="Download per-section stems as ZIP"
            >{{ zipLoading === `${response.generation_id}:sections` ? '…' : 'Sections ZIP' }}</button>
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
                  :disabled="isRecording"
                  @click.stop="handleOfflineExport(response, 'wav')"
                  title="Offline render — full mix as WAV (fast). Progress also shows in the ⬇ header button."
                >WAV ⚡</button>
                <button
                  class="seed-action"
                  :disabled="isRecording"
                  @click.stop="handleOfflineExport(response, 'stems')"
                  title="Offline render — drums / bass / melodic as separate WAV files (fast). Progress also shows in the ⬇ header button."
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
import { useMidiPlayer, type PlayerPart } from '../composables/useMidiPlayer'
import { useDownloadPrompt } from '../composables/useDownloadPrompt'
import { useRenderQueue } from '../composables/useRenderQueue'
import { logError } from '../composables/useErrorLog'
import { resolveProgression } from '../utils/chordResolver'

const props = defineProps<{ history: GenerateResponse[]; loading?: boolean; starredIds?: Set<string> }>()
const emit = defineEmits<{
  (e: 'replay', response: GenerateResponse): void
  (e: 'part-regenned', genId: string, file: FileInfo): void
  (e: 'toggle-star', genId: string): void
  (e: 'delete', genId: string): void
  (e: 'clear'): void
}>()

const { isRecording, offlineRender } = useMidiPlayer()
const { promptFilename } = useDownloadPrompt()
const { startJob, updateProgress, completeJob, failJob } = useRenderQueue()
const zipLoading = ref<string | null>(null)
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
    logError('Regenerate part', e)
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

async function handleOfflineExport(response: GenerateResponse, mode: 'wav' | 'stems') {
  const combinedFile = response.files.find(f => f.part === 'combined')
  if (!combinedFile) return
  const defaultName = `${response.style}_${response.generation_id.slice(0, 8)}`
  const name = await promptFilename(
    defaultName, 'wav', mode === 'wav' ? 'Export as WAV' : 'Export stems as WAV',
  )
  if (name === null) return   // cancelled

  exportingId.value = response.generation_id
  exportProgress.value = 0
  exportStem.value = null
  const durationSeconds = response.summary.bars * (4 * 60 / response.summary.bpm)
  const label = formatStyle(response.style)
  // Each file gets its own render-queue entry (in addition to the local
  // exportingId/exportProgress UI here) so progress and completion stay visible
  // from the ⬇ header button even if this panel entry gets collapsed or this
  // whole component unmounts before the render finishes.
  try {
    if (mode === 'wav') {
      const jobId = startJob(`${label} — ${name}`, `${name}.wav`)
      try {
        const blob = await offlineRender(combinedFile.url, response.style, durationSeconds, 'all', v => {
          exportProgress.value = v
          updateProgress(jobId, v)
        })
        completeJob(jobId, blob)
      } catch (e) {
        failJob(jobId, e instanceof Error ? e.message : 'WAV export failed')
        throw e
      }
    } else {
      // One WAV per part actually present in this generation (true per-part
      // stems, not the old drums/bass/melodic buckets). The chosen name becomes
      // a shared prefix — individual stem names still distinguish the files.
      const stems = response.files
        .map(f => f.part)
        .filter(p => p !== 'combined' && p !== 'song') as PlayerPart[]
      for (let i = 0; i < stems.length; i++) {
        const stem = stems[i]
        exportStem.value = stem
        exportProgress.value = 0
        const jobId = startJob(`${stem} — ${name}`, `${name}_${stem}.wav`)
        try {
          const blob = await offlineRender(combinedFile.url, response.style, durationSeconds, stem, v => {
            exportProgress.value = (i + v) / stems.length
            updateProgress(jobId, v)
          })
          completeJob(jobId, blob)
        } catch (e) {
          failJob(jobId, e instanceof Error ? e.message : 'WAV export failed')
          throw e
        }
      }
    }
  } catch (e: any) {
    regenError.value = e.message ?? 'Export failed'
    logError('WAV/stems export', e)
  } finally {
    exportingId.value = null
    exportProgress.value = 0
    exportStem.value = null
  }
}

async function handleZipDownload(response: GenerateResponse, kind: 'bundle' | 'sections') {
  const key = `${response.generation_id}:${kind}`
  if (zipLoading.value === key) return
  const defaultName = kind === 'bundle'
    ? `${response.style}_${response.generation_id.slice(0, 8)}`
    : `${response.style}_${response.generation_id.slice(0, 8)}_sections`
  const name = await promptFilename(defaultName, 'zip', 'Download ZIP')
  if (name === null) return   // cancelled

  zipLoading.value = key
  const jobId = startJob(`${formatStyle(response.style)} — ${name}`, `${name}.zip`)
  try {
    const res = await fetch(kind === 'bundle' ? bundleUrl(response.generation_id) : sectionsUrl(response.generation_id))
    if (!res.ok) throw new Error('Download failed')
    const blob = await res.blob()
    completeJob(jobId, blob)
  } catch (e: any) {
    failJob(jobId, e.message ?? 'Download failed')
    regenError.value = e.message ?? 'Download failed'
    logError('ZIP download', e)
  } finally {
    zipLoading.value = null
  }
}
</script>

<style scoped>
@keyframes shimmer {
  0%   { background-position: -400px 0; }
  100% { background-position: 400px 0; }
}

.skeleton-card {
  background: var(--panel);
  border: 1px solid var(--surface);
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
  background: linear-gradient(90deg, var(--surface) 25%, var(--surface-hover) 50%, var(--surface) 75%);
  background-size: 800px 100%;
  animation: shimmer 1.4s infinite linear;
}

.generating-banner {
  font-size: 0.72rem;
  color: var(--accent);
  text-align: center;
  padding: 0.35rem;
  margin-bottom: 0.5rem;
  border: 1px solid color-mix(in srgb, var(--accent) 20%, transparent);
  border-radius: 6px;
  background: var(--surface-muted);
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
  color: var(--text-dim);
}

.history-count {
  font-size: 0.7rem;
  background: var(--surface);
  color: var(--text-dim);
  border-radius: 10px;
  padding: 0.1rem 0.5rem;
}

.history-search {
  flex: 1;
  max-width: 120px;
  background: var(--panel-deep);
  border: 1px solid var(--surface);
  border-radius: 4px;
  color: var(--text);
  font-size: 0.72rem;
  padding: 0.2rem 0.5rem;
  outline: none;
}
.history-search:focus { border-color: color-mix(in srgb, var(--accent) 33%, transparent); }
.history-search::placeholder { color: var(--text-faint); }

.entry-name {
  font-size: 0.7rem;
  color: var(--text-faint);
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
.entry-name.has-name { color: var(--text-dim); }
.entry-name:focus { border-color: color-mix(in srgb, var(--accent) 27%, transparent); background: var(--panel-deep); color: var(--text); }
.entry-name[contenteditable="true"] { cursor: text; }

.arrange-toggle {
  margin-left: auto;
  font-size: 0.68rem;
  padding: 0.2rem 0.6rem;
  background: var(--panel-deep);
  border: 1px solid var(--surface);
  border-radius: 4px;
  color: var(--text-dim);
  cursor: pointer;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}
.arrange-toggle:hover { background: var(--panel-alt); color: var(--text); }
.arrange-toggle.active { border-color: color-mix(in srgb, var(--accent) 27%, transparent); color: var(--accent); }

.history-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.history-entry {
  background: var(--panel);
  border: 1px solid var(--surface);
  border-radius: 10px;
  overflow: hidden;
  transition: border-color 0.15s;
}

.history-entry.expanded {
  border-color: var(--accent);
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
  color: var(--text);
  cursor: pointer;
  text-align: left;
}

.history-row:hover { background: var(--panel-alt); }

.star-btn {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 1rem;
  color: var(--text-faint);
  padding: 0 0.1rem;
  line-height: 1;
  transition: color 0.15s, transform 0.1s;
  flex-shrink: 0;
}
.star-btn:hover { color: var(--gold); transform: scale(1.2); }
.star-btn.starred { color: var(--gold); }

.entry-style {
  font-weight: 600;
  font-size: 0.9rem;
  min-width: 100px;
}

.entry-meta {
  font-size: 0.8rem;
  color: var(--text-dim);
  flex: 1;
  display: flex;
  align-items: center;
  gap: 0.4rem;
  flex-wrap: wrap;
}

.entry-section {
  font-size: 0.65rem;
  font-weight: 600;
  color: var(--accent);
  background: var(--surface-muted);
  border: 1px solid color-mix(in srgb, var(--accent) 27%, transparent);
  border-radius: 3px;
  padding: 0.05rem 0.4rem;
  white-space: nowrap;
}

.entry-id {
  font-size: 0.72rem;
  font-family: monospace;
  color: var(--text-faint);
}

.entry-chevron {
  font-size: 0.65rem;
  color: var(--text-faint);
}

.clear-btn {
  font-size: 0.68rem;
  padding: 0.2rem 0.6rem;
  background: var(--panel-deep);
  border: 1px solid var(--surface);
  border-radius: 4px;
  color: var(--text-dim);
  cursor: pointer;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}
.clear-btn:hover { background: var(--error-surface); color: var(--error); border-color: color-mix(in srgb, var(--error) 27%, transparent); }

.entry-del {
  background: none;
  border: none;
  color: var(--text-faint);
  font-size: 0.8rem;
  cursor: pointer;
  padding: 0 0.2rem;
  line-height: 1;
  flex-shrink: 0;
  transition: color 0.15s;
}
.entry-del:hover { color: var(--error); }

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
  background: var(--panel-deep);
  border-radius: 6px;
  border: 1px solid var(--surface);
}

.seed-label {
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-faint);
}

.seed-value {
  font-family: monospace;
  font-size: 0.82rem;
  color: var(--accent);
  flex: 1;
}

.seed-action {
  font-size: 0.75rem;
  padding: 0.2rem 0.6rem;
  background: var(--surface);
  border: 1px solid var(--surface-hover);
  border-radius: 4px;
  color: var(--text-dim);
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.seed-action:hover { background: var(--surface-hover); color: var(--text); }

.seed-action.replay {
  color: var(--accent);
  border-color: color-mix(in srgb, var(--accent) 27%, transparent);
}

.seed-action.replay:hover { background: var(--accent-surface-strong); color: var(--accent-bright); }

.seed-action.save {
  color: var(--success);
  border-color: color-mix(in srgb, var(--success) 27%, transparent);
}

.seed-action.save:hover:not(:disabled) { background: var(--success-surface); color: var(--success); }

.seed-action.save.saved {
  color: var(--text-faint);
  border-color: var(--surface);
  cursor: default;
}

.seed-action:disabled { opacity: 0.6; cursor: default; }

.export-progress {
  font-size: 0.75rem;
  padding: 0.2rem 0.6rem;
  background: var(--surface-muted);
  border: 1px solid color-mix(in srgb, var(--accent) 27%, transparent);
  border-radius: 4px;
  color: var(--accent);
  font-family: monospace;
}

.regen-error {
  font-size: 0.75rem;
  color: var(--error);
  padding: 0.3rem 0.5rem;
  background: var(--error-surface);
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
  background: var(--panel-deep);
  border-radius: 6px;
  border: 1px solid var(--surface);
}

.prog-label {
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-faint);
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
  color: var(--accent-bright);
  letter-spacing: 0.03em;
}

.prog-resolved {
  font-family: monospace;
  font-size: 0.72rem;
  color: var(--text-dim);
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
  color: var(--text-faint);
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
.rate-btn.active { opacity: 1; border-color: color-mix(in srgb, var(--accent) 27%, transparent); }
</style>
