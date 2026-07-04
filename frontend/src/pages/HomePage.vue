<!--
  GenreGrid — a style-based MIDI generator.
  Copyright (C) 2026 Tw Dover

  This program is free software: you can redistribute it and/or modify it under
  the terms of the GNU General Public License v3 or (at your option) any later
  version. Distributed WITHOUT ANY WARRANTY. See <https://www.gnu.org/licenses/>.
-->
<template>
  <div class="home-page">
    <header class="app-header">
      <div class="header-title">
        <h1>GenreGrid</h1>
        <p class="subtitle">
          <span class="subtitle-text" :class="{ hidden: showCredit }">Style-based MIDI generator</span>
          <span class="subtitle-credit" :class="{ visible: showCredit }">by TW Dover</span>
        </p>
      </div>
      <NowPlayingBar />
      <div class="header-actions">
        <button class="hdr-btn" @click="saveSession" title="Save session (Ctrl+S)">Save</button>
        <label class="hdr-btn" title="Load session from file">
          Load
          <input ref="loadInput" type="file" accept=".json" style="display:none" @change="loadSession" />
        </label>
        <button class="hdr-btn hdr-help" @click="showShortcuts = !showShortcuts" title="Keyboard shortcuts">?</button>
      </div>
      <div class="volume-control">
        <span class="vol-icon">{{ volume === 0 ? '🔇' : volume < 40 ? '🔈' : '🔊' }}</span>
        <input
          type="range"
          min="0"
          max="100"
          :value="volume"
          @input="setVolume(+($event.target as HTMLInputElement).value)"
          class="vol-slider"
          title="Master volume"
        />
      </div>
    </header>

    <main class="app-main">
      <section class="form-section">
        <GenerateForm :styles="styles" :loading="loading || batchLoading" :replayData="replayData" @submit="handleGenerate" @batch="handleBatch" @refresh-styles="refreshStyles" />
        <div v-if="genProgress && loading" class="progress-row">
          <span class="progress-text">{{ genProgress }}</span>
          <div class="progress-dots"><span>.</span><span>.</span><span>.</span></div>
        </div>
        <div v-if="error && !loading" class="error-row">
          <p class="error-msg">{{ error }}</p>
          <button class="retry-btn" @click="retryFetch">Retry</button>
        </div>
      </section>

      <section class="export-section">
        <div class="panel-tabs">
          <button class="panel-tab" :class="{ active: activePanel === 'history' }" @click="activePanel = 'history'">History</button>
          <button class="panel-tab" :class="{ active: activePanel === 'library' }" @click="activePanel = 'library'">Library</button>
          <button class="panel-tab panel-tab-song" :class="{ active: activePanel === 'song' }" @click="activePanel = 'song'">Song</button>
        </div>
        <ExportPanel v-if="activePanel === 'history'" :history="history" :loading="loading" :starredIds="starredIds" @replay="handleReplay" @part-regenned="handlePartRegenned" @toggle-star="handleToggleStar" />
        <LibraryPanel v-else-if="activePanel === 'library'" :styles="styles" @replay="handleLibraryReplay" />
        <SongBuilder v-else :styles="styles" />
      </section>
    </main>

    <div v-if="showShortcuts" class="shortcuts-overlay" @click.self="showShortcuts = false">
      <div class="shortcuts-modal">
        <div class="shortcuts-header">
          <span class="shortcuts-title">Keyboard Shortcuts</span>
          <button class="close-btn" @click="showShortcuts = false">✕</button>
        </div>
        <table class="shortcuts-table">
          <tbody>
            <tr><td class="shortcut-key">Space</td><td class="shortcut-desc">Stop playback</td></tr>
            <tr><td class="shortcut-key">Ctrl+S</td><td class="shortcut-desc">Save session</td></tr>
            <tr><td class="shortcut-key">?</td><td class="shortcut-desc">Show shortcuts</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'
import GenerateForm from '../components/GenerateForm.vue'
import ExportPanel from '../components/ExportPanel.vue'
import LibraryPanel from '../components/LibraryPanel.vue'
import NowPlayingBar from '../components/NowPlayingBar.vue'
import SongBuilder from '../components/SongBuilder.vue'
import { fetchStyles, generate, batchGenerate } from '../services/api'
import type { StyleInfo, GenerateRequest, GenerateResponse, FileInfo, LibraryEntry } from '../types/midi'
import { useMidiPlayer } from '../composables/useMidiPlayer'

const { volume, setVolume, prefetchSamplers, stop, currentlyPlaying } = useMidiPlayer()

const showCredit = ref(false)
const showShortcuts = ref(false)
const loadInput = ref<HTMLInputElement | null>(null)
let _creditTimer: ReturnType<typeof setTimeout> | null = null

const styles = ref<StyleInfo[]>([])
const loading = ref(false)
const batchLoading = ref(false)
const genProgress = ref<string | null>(null)
const error = ref<string | null>(null)

const loadHistory = (): GenerateResponse[] => {
  try {
    return JSON.parse(localStorage.getItem('genregrid_history') ?? '[]')
  } catch {
    return []
  }
}
const loadStarred = (): Set<string> => {
  try {
    return new Set(JSON.parse(localStorage.getItem('genregrid_starred') ?? '[]'))
  } catch {
    return new Set()
  }
}

const history = ref<GenerateResponse[]>(loadHistory())
const starredIds = ref<Set<string>>(loadStarred())
const replayData = ref<GenerateResponse | null>(null)
const activePanel = ref<'history' | 'library' | 'song'>('history')

watch(history, (val) => {
  localStorage.setItem('genregrid_history', JSON.stringify(val))
}, { immediate: false, deep: true })

watch(starredIds, (val) => {
  localStorage.setItem('genregrid_starred', JSON.stringify([...val]))
}, { deep: true })

function handleToggleStar(genId: string) {
  const next = new Set(starredIds.value)
  if (next.has(genId)) next.delete(genId)
  else next.add(genId)
  starredIds.value = next
}

function saveSession() {
  const data = JSON.stringify({
    version: 1,
    history: history.value,
    starred: [...starredIds.value],
  }, null, 2)
  const blob = new Blob([data], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `genregrid-session-${new Date().toISOString().slice(0, 10)}.json`
  a.click()
  URL.revokeObjectURL(url)
}

function loadSession(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = ev => {
    try {
      const data = JSON.parse(ev.target?.result as string)
      if (data.history) history.value = data.history
      if (data.starred) starredIds.value = new Set(data.starred)
    } catch { /* ignore malformed */ }
  }
  reader.readAsText(file)
}

function onKeyDown(e: KeyboardEvent) {
  const tag = (e.target as HTMLElement).tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
  if (e.key === ' ' && currentlyPlaying.value) {
    e.preventDefault()
    stop()
  }
  if (e.key === 's' && (e.ctrlKey || e.metaKey)) {
    e.preventDefault()
    saveSession()
  }
  if (e.key === '?' || (e.key === '/' && e.shiftKey)) {
    e.preventDefault()
    showShortcuts.value = !showShortcuts.value
  }
}
onMounted(() => {
  window.addEventListener('keydown', onKeyDown)
  _creditTimer = setTimeout(() => {
    showCredit.value = true
    _creditTimer = setTimeout(() => { showCredit.value = false }, 3500)
  }, 2000)
})
onUnmounted(() => {
  window.removeEventListener('keydown', onKeyDown)
  if (_creditTimer) clearTimeout(_creditTimer)
})

onMounted(async () => {
  try {
    styles.value = await fetchStyles()
    const params = new URLSearchParams(window.location.search)
    if (params.get('seed')) {
      replayData.value = {
        generation_id: '',
        style: params.get('style') ?? styles.value[0]?.id ?? 'lofi',
        files: [],
        summary: {
          key: `${params.get('key') ?? 'C'} ${params.get('scale') ?? 'minor'}`,
          key_root: params.get('key') ?? 'C',
          scale: params.get('scale') ?? 'minor',
          bpm: Number(params.get('bpm') ?? 120),
          bars: Number(params.get('bars') ?? 8),
          complexity: 0.5,
          variation: 0.4,
          mode: params.get('mode') ?? 'loop',
        },
        seed: Number(params.get('seed')),
        auto_saved: false,
      }
    }
  } catch (e) {
    error.value = 'Could not reach backend — make sure uvicorn is running on port 8000.'
  }
})

async function handleGenerate(form: GenerateRequest) {
  loading.value = true
  error.value = null
  genProgress.value = null
  try {
    const t0 = Date.now()
    const result = await generate(form, (attempt, total) => {
      genProgress.value = `Attempt ${attempt}/${total}…`
    })
    result._elapsed = ((Date.now() - t0) / 1000).toFixed(1)
    const merged = [result, ...history.value]
    const starred = merged.filter(r => starredIds.value.has(r.generation_id))
    const unstarred = merged.filter(r => !starredIds.value.has(r.generation_id)).slice(0, 10)
    history.value = [...starred, ...unstarred].slice(0, 50)
    prefetchSamplers(result.style)
    activePanel.value = 'history'
    const params = new URLSearchParams({
      style: result.style,
      key: result.summary.key_root,
      scale: result.summary.scale,
      bpm: String(result.summary.bpm),
      bars: String(result.summary.bars),
      seed: String(result.seed),
      mode: result.summary.mode,
    })
    window.history.replaceState({}, '', `?${params}`)
  } catch (e: any) {
    error.value = e.message ?? 'Unknown error'
  } finally {
    loading.value = false
    genProgress.value = null
  }
}

async function retryFetch() {
  error.value = null
  try {
    styles.value = await fetchStyles()
  } catch (e) {
    error.value = 'Could not reach backend — make sure uvicorn is running on port 8000.'
  }
}

function handleReplay(response: GenerateResponse) {
  replayData.value = null
  setTimeout(() => { replayData.value = response }, 0)
}

async function handleLibraryReplay(entry: LibraryEntry) {
  const req: GenerateRequest = {
    style_id: entry.style_id,
    key: entry.key,
    scale: entry.scale,
    bpm: entry.bpm,
    bars: entry.bars,
    complexity: 0.5,
    variation: 0.4,
    humanize: 0.5,
    blend_amount: 0.5,
    parts: ['chords', 'bass', 'melody', 'drums'],
    mode: 'loop',
    seed: entry.seed,
  }
  // Pre-fill the form so the user can tweak and re-generate
  replayData.value = null
  setTimeout(() => {
    replayData.value = {
      generation_id: entry.gen_id,
      style: entry.style_id,
      files: [],
      summary: { key: `${entry.key} ${entry.scale}`, key_root: entry.key, scale: entry.scale,
                 bpm: entry.bpm, bars: entry.bars, complexity: 0.5, variation: 0.4, mode: 'loop' },
      seed: entry.seed,
      quality: entry.quality,
      auto_saved: true,
    }
  }, 0)
  await handleGenerate(req)
}

async function handleBatch(form: GenerateRequest, count: number) {
  batchLoading.value = true
  error.value = null
  try {
    const results = await batchGenerate({ base: form, count })
    for (const result of results) {
      result._elapsed = undefined
      const merged = [result, ...history.value]
      const starred = merged.filter(r => starredIds.value.has(r.generation_id))
      const unstarred = merged.filter(r => !starredIds.value.has(r.generation_id)).slice(0, 10)
      history.value = [...starred, ...unstarred].slice(0, 50)
    }
    prefetchSamplers(form.style_id)
    activePanel.value = 'history'
  } catch (e: any) {
    error.value = e.message ?? 'Batch generation failed'
  } finally {
    batchLoading.value = false
  }
}

async function refreshStyles() {
  try {
    styles.value = await fetchStyles()
  } catch {
    // ignore — styles list is stale but still usable
  }
}

function handlePartRegenned(genId: string, newFile: FileInfo) {
  const entry = history.value.find(r => r.generation_id === genId)
  if (!entry) return
  const v = Date.now()
  const idx = entry.files.findIndex(f => f.part === newFile.part)
  if (idx >= 0) {
    entry.files[idx] = { ...newFile, url: `${newFile.url}?v=${v}` }
  }
  // Bust the combined cache too — the backend rebuilds combined.mid on every regen
  const combinedIdx = entry.files.findIndex(f => f.part === 'combined')
  if (combinedIdx >= 0) {
    const combined = entry.files[combinedIdx]
    const baseUrl = combined.url.split('?')[0]
    entry.files[combinedIdx] = { ...combined, url: `${baseUrl}?v=${v}` }
  }
}
</script>

<style scoped>
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}

.header-title h1,
.header-title .subtitle {
  margin: 0;
}

.subtitle {
  position: relative;
  height: 1.2em;
}

.subtitle-text,
.subtitle-credit {
  position: absolute;
  left: 0;
  top: 0;
  transition: opacity 0.8s ease;
  white-space: nowrap;
}

.subtitle-text { opacity: 1; }
.subtitle-text.hidden { opacity: 0; }

.subtitle-credit {
  opacity: 0;
  color: #2a6070;
  font-style: italic;
}
.subtitle-credit.visible { opacity: 1; }

.header-actions {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  flex-shrink: 0;
}

.hdr-btn {
  font-size: 0.72rem;
  padding: 0.25rem 0.6rem;
  background: #060f14;
  border: 1px solid #0d2535;
  border-radius: 5px;
  color: #4a7080;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
  white-space: nowrap;
  user-select: none;
}
.hdr-btn:hover { background: #0d2535; color: #e0e0e8; }

.hdr-help {
  font-weight: 700;
  width: 24px;
  padding: 0.25rem 0;
  text-align: center;
}

.shortcuts-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.65);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 200;
}

.shortcuts-modal {
  background: #060f14;
  border: 1px solid #0d2535;
  border-radius: 12px;
  padding: 1.25rem 1.5rem;
  min-width: 280px;
}

.shortcuts-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1rem;
}

.shortcuts-title {
  font-size: 0.85rem;
  font-weight: 600;
  color: #e0e0e8;
  letter-spacing: 0.04em;
}

.close-btn {
  background: none;
  border: none;
  color: #4a7080;
  font-size: 0.9rem;
  cursor: pointer;
  padding: 0.2rem 0.4rem;
  border-radius: 4px;
  transition: color 0.15s;
}
.close-btn:hover { color: #e0e0e8; }

.shortcuts-table {
  border-collapse: collapse;
  width: 100%;
}

.shortcut-key {
  font-family: monospace;
  font-size: 0.78rem;
  color: #00c8ff;
  background: #001520;
  border: 1px solid #0d2535;
  border-radius: 4px;
  padding: 0.2rem 0.5rem;
  white-space: nowrap;
}

.shortcut-desc {
  font-size: 0.8rem;
  color: #7ae8ff;
  padding-left: 1rem;
}

.shortcuts-table tr { height: 2rem; }

.volume-control {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-shrink: 0;
}

.vol-icon {
  font-size: 1rem;
  width: 1.4rem;
  text-align: center;
}

.vol-slider {
  -webkit-appearance: none;
  appearance: none;
  width: 90px;
  height: 4px;
  border-radius: 2px;
  background: #122f40;
  outline: none;
  cursor: pointer;
}

.vol-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #00c8ff;
  cursor: pointer;
}

.vol-slider::-moz-range-thumb {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #00c8ff;
  cursor: pointer;
  border: none;
}

.progress-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.75rem;
  color: #00c8ff;
}

@keyframes dot-blink {
  0%, 80%, 100% { opacity: 0.2; }
  40% { opacity: 1; }
}
.progress-dots span { animation: dot-blink 1.4s infinite; }
.progress-dots span:nth-child(2) { animation-delay: 0.2s; }
.progress-dots span:nth-child(3) { animation-delay: 0.4s; }

.error-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.retry-btn {
  font-size: 0.75rem;
  padding: 0.2rem 0.6rem;
  background: #0d2535;
  border: 1px solid #122f40;
  border-radius: 4px;
  color: #4a7080;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
  white-space: nowrap;
}

.retry-btn:hover {
  background: #122f40;
  color: #e0e0e8;
}

.panel-tabs {
  display: flex;
  gap: 0.25rem;
  margin-bottom: 0.75rem;
}

.panel-tab {
  font-size: 0.78rem;
  padding: 0.3rem 0.9rem;
  background: #060f14;
  border: 1px solid #0d2535;
  border-radius: 6px;
  color: #4a7080;
  cursor: pointer;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}

.panel-tab:hover { background: #081620; color: #e0e0e8; }

.panel-tab.active {
  background: #001e35;
  border-color: #00c8ff;
  color: #7ae8ff;
}

.panel-tab-song.active {
  border-color: #00c8ff;
  background: #001e35;
  color: #7ae8ff;
}
</style>
