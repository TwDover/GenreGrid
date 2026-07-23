<!--
  GenreGrid — a style-based MIDI generator.
  Copyright (C) 2026 Tw Dover

  This program is free software: you can redistribute it and/or modify it under
  the terms of the GNU General Public License v3 or (at your option) any later
  version. Distributed WITHOUT ANY WARRANTY. See <https://www.gnu.org/licenses/>.
-->
<template>
  <div class="app-shell">
    <!-- ── Topbar ─────────────────────────────────────────────────────────── -->
    <header class="topbar">
      <div class="brand">Genre<span>Grid</span></div>

      <button class="btn" @click="openSetup" aria-haspopup="dialog">
        <span aria-hidden="true">⚙</span> Setup
      </button>
      <button class="btn" @click="drawer = 'library'" aria-haspopup="dialog">
        {{ mode === 'song' ? 'Songs' : 'Library' }}
      </button>

      <div class="spacer"></div>

      <button
        v-if="isElectron"
        class="btn btn-quiet"
        :disabled="updateChecking"
        @click="checkForUpdates"
        :title="updateMessage || 'Check for a newer version'"
      >{{ updateLabel }}</button>
      <button
        v-if="renderJobs.length"
        class="btn btn-quiet"
        :class="{ 'topbar-active': activeRenderCount > 0 }"
        @click="openRenderQueue"
        :title="activeRenderCount > 0 ? `${activeRenderCount} download${activeRenderCount === 1 ? '' : 's'} in progress` : 'Download history'"
      >⬇ {{ activeRenderCount > 0 ? activeRenderCount : renderJobs.length }}</button>
      <button
        v-if="errorEntries.length"
        class="btn btn-quiet topbar-error"
        @click="openErrorLog"
        :title="`${errorEntries.length} error${errorEntries.length === 1 ? '' : 's'} logged this session`"
      >🐛 {{ errorEntries.length }}</button>
      <button class="btn btn-quiet btn-icon" @click="cycleTheme" :title="`Theme: ${THEME_META[theme].label} — click to cycle`">{{ THEME_META[theme].icon }}</button>
      <button class="btn btn-quiet btn-icon" @click="showHelp = true" title="How GenreGrid works">?</button>
      <button class="btn btn-quiet btn-icon" @click="showShortcuts = !showShortcuts" title="Keyboard shortcuts">⌨</button>
    </header>

    <!-- ── Workspace: the only scroll region ──────────────────────────────── -->
    <main class="workspace">
      <div class="workspace-inner">
        <ExportPanel
          v-if="mode !== 'song'"
          :history="history" :loading="loading" :starredIds="starredIds"
          @replay="handleReplay" @part-regenned="handlePartRegenned"
          @toggle-star="handleToggleStar" @delete="deleteHistoryEntry" @clear="clearHistory"
          @open-setup="openSetup"
        />
        <SongResult v-else :result="songResult" :label="songLabel" @rebuilt="onSongBuilt" @open-setup="openSetup" />
      </div>
    </main>

    <!-- ── Docked transport ───────────────────────────────────────────────── -->
    <TransportBar />

    <!-- ═══ Drawers ═══════════════════════════════════════════════════════ -->
    <div class="scrim" :class="{ open: !!drawer }" @click="closeDrawer"></div>

    <!-- Setup: wide sheet from the top -->
    <section class="sheet sheet-top" :class="{ open: drawer === 'setup' }" role="dialog" aria-modal="true" aria-label="Setup">
      <div class="sheet-head">
        <span class="sheet-title">Setup</span>
        <div class="spacer"></div>
        <button class="btn btn-quiet btn-icon" @click="closeDrawer" title="Close">✕</button>
      </div>
      <div class="sheet-body">
        <!-- What kind of thing are we generating? Spelled out so the three
             words aren't left to explain themselves. -->
        <div class="mode-picker">
          <span class="mode-picker-label">What do you want to make?</span>
          <div class="mode-cards">
            <button
              v-for="m in (['loop','arrangement','song'] as const)"
              :key="m"
              class="mode-card"
              :class="{ active: mode === m }"
              :aria-pressed="mode === m"
              @click="mode = m"
            >
              <span class="mc-title">{{ MODE_LABELS[m] }}</span>
              <span class="mc-desc">{{ MODE_HINTS[m] }}</span>
            </button>
          </div>
        </div>

        <GenerateForm
          v-if="mode !== 'song'"
          :styles="styles"
          :loading="loading || batchLoading"
          :replayData="replayData"
          :forcedMode="genMode"
          @submit="handleGenerate"
          @batch="handleBatch"
          @refresh-styles="refreshStyles"
        />
        <SongForm v-else :styles="styles" @built="onSongBuilt" />

        <div v-if="genProgress && loading && mode !== 'song'" class="progress-row">
          <span>{{ genProgress }}</span>
          <div class="progress-dots"><span>.</span><span>.</span><span>.</span></div>
        </div>
        <div v-if="error && !loading && mode !== 'song'" class="error-row">
          <p class="error-msg">{{ error }}</p>
          <button class="btn btn-quiet" @click="retryFetch">Retry</button>
        </div>
      </div>
    </section>

    <!-- Songs / Library: rail from the right -->
    <section class="sheet sheet-right" :class="{ open: drawer === 'library' }" role="dialog" aria-modal="true" :aria-label="mode === 'song' ? 'Songs' : 'Library'">
      <div class="sheet-head">
        <span class="sheet-title">{{ mode === 'song' ? 'Songs' : 'Library' }}</span>
        <button v-if="mode === 'song' && songHistory.length" class="btn btn-quiet clear-btn" @click="clearSongs" title="Clear recent songs">Clear</button>
        <div class="spacer"></div>
        <button class="btn btn-quiet btn-icon" @click="closeDrawer" title="Close">✕</button>
      </div>
      <div class="sheet-body">
        <template v-if="mode === 'song'">
          <div v-if="!songHistory.length" class="rail-empty">Songs you build show up here.</div>
          <div v-else class="song-list">
            <div
              v-for="item in songHistory"
              :key="item.result.generation_id"
              class="song-item"
              role="button" tabindex="0"
              :aria-current="item.result.generation_id === songResult?.generation_id"
              @click="loadSong(item); closeDrawer()"
              @keydown.enter="loadSong(item); closeDrawer()"
            >
              <span class="si-label">{{ item.label }}</span>
              <span class="si-meta mono">{{ item.result.total_bars }} bars · {{ item.result.bpm }} BPM · {{ item.result.key }}</span>
              <button class="si-del" @click.stop="deleteSong(item.result.generation_id)" title="Remove">✕</button>
            </div>
          </div>
        </template>
        <LibraryPanel v-else :styles="styles" @replay="entry => { handleLibraryReplay(entry) }" />
      </div>
      <div class="sheet-foot">
        <span class="eyebrow">Session</span>
        <button class="btn btn-quiet" @click="saveSession" title="Save history &amp; pins to a file (Ctrl+S)">Save</button>
        <label class="btn btn-quiet" title="Load session from file">
          Load
          <input ref="loadInput" type="file" accept=".json" style="display:none" @change="loadSession" />
        </label>
      </div>
    </section>

    <!-- ── Shortcuts modal ────────────────────────────────────────────────── -->
    <div v-if="showShortcuts" class="shortcuts-overlay" @click.self="showShortcuts = false">
      <div class="shortcuts-modal">
        <div class="shortcuts-header">
          <span class="shortcuts-title">Keyboard Shortcuts</span>
          <button class="btn btn-quiet btn-icon" @click="showShortcuts = false">✕</button>
        </div>
        <table class="shortcuts-table">
          <tbody>
            <tr><td class="shortcut-key">Space</td><td class="shortcut-desc">Stop playback</td></tr>
            <tr><td class="shortcut-key">Ctrl+S</td><td class="shortcut-desc">Save session</td></tr>
            <tr><td class="shortcut-key">Esc</td><td class="shortcut-desc">Close drawer / dialog</td></tr>
            <tr><td class="shortcut-key">?</td><td class="shortcut-desc">How GenreGrid works</td></tr>
            <tr><td colspan="2" class="shortcut-section">Developer / Debug</td></tr>
            <tr><td class="shortcut-key">Ctrl/Cmd+Shift+D</td><td class="shortcut-desc">Toggle on-screen debug HUD (mirrors console)</td></tr>
            <tr><td class="shortcut-key">F12 / Ctrl+Shift+I</td><td class="shortcut-desc">Toggle DevTools</td></tr>
            <tr><td class="shortcut-key">Ctrl/Cmd+R</td><td class="shortcut-desc">Reload</td></tr>
            <tr><td class="shortcut-key">Ctrl/Cmd+Shift+R</td><td class="shortcut-desc">Hard reload (ignore cache)</td></tr>
            <tr><td class="shortcut-key">Ctrl/Cmd + = / -</td><td class="shortcut-desc">Zoom in / out</td></tr>
            <tr><td class="shortcut-key">Ctrl/Cmd+0</td><td class="shortcut-desc">Reset zoom</td></tr>
            <tr><td class="shortcut-key">F11</td><td class="shortcut-desc">Toggle fullscreen</td></tr>
            <tr><td class="shortcut-key">Ctrl/Cmd+M</td><td class="shortcut-desc">Minimize window</td></tr>
            <tr><td class="shortcut-key">Ctrl/Cmd+W / Q</td><td class="shortcut-desc">Quit</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <HelpPanel v-if="showHelp" @close="showHelp = false" />

    <ToastHost />
    <DownloadNamePrompt />
    <ErrorLogPanel />
    <RenderQueuePanel />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import GenerateForm from '../components/GenerateForm.vue'
import ExportPanel from '../components/ExportPanel.vue'
import LibraryPanel from '../components/LibraryPanel.vue'
import TransportBar from '../components/TransportBar.vue'
import SongForm from '../components/SongForm.vue'
import SongResult from '../components/SongResult.vue'
import HelpPanel from '../components/HelpPanel.vue'
import ToastHost from '../components/ToastHost.vue'
import DownloadNamePrompt from '../components/DownloadNamePrompt.vue'
import ErrorLogPanel from '../components/ErrorLogPanel.vue'
import RenderQueuePanel from '../components/RenderQueuePanel.vue'
import { useErrorLog } from '../composables/useErrorLog'
import { setStyleCatalog } from '../composables/useStyleCatalog'
import { useRenderQueue } from '../composables/useRenderQueue'
import { fetchStyles, generate, batchGenerate, listSongs } from '../services/api'
import type { StyleInfo, GenerateRequest, GenerateResponse, FileInfo, LibraryEntry, BuildSongResponse } from '../types/midi'
import { useMidiPlayer } from '../composables/useMidiPlayer'
import { useTheme } from '../composables/useTheme'

const { prefetchSamplers, stop, currentlyPlaying } = useMidiPlayer()
const { theme, cycleTheme, THEME_META } = useTheme()
const { entries: errorEntries, open: openErrorLog } = useErrorLog()
const { jobs: renderJobs, open: openRenderQueue } = useRenderQueue()
const activeRenderCount = computed(() => renderJobs.value.filter(j => j.status === 'rendering').length)

const showShortcuts = ref(false)
const showHelp = ref(false)

// Which drawer is open, if any. Setup (top) holds the form; library (right)
// holds recent songs / the saved-styles library.
const drawer = ref<'setup' | 'library' | null>(null)
function openSetup() { drawer.value = 'setup' }
function closeDrawer() { drawer.value = null }

// ── Manual update check (desktop app only) ───────────────────────────────────
const isElectron = typeof window !== 'undefined' && !!(window as any).electronAPI
const updateChecking = ref(false)
const updateLabel = ref('Updates')
const updateMessage = ref('')

async function checkForUpdates() {
  if (updateChecking.value) return
  updateChecking.value = true
  updateLabel.value = 'Checking…'
  updateMessage.value = ''
  try {
    const r = await (window as any).electronAPI.checkForUpdates()
    switch (r.status) {
      case 'downloading':
        updateLabel.value = `↓ v${r.latest}`
        updateMessage.value = `Downloading v${r.latest} — you'll be offered a restart when it's ready`
        break
      case 'uptodate':
        updateLabel.value = 'Up to date ✓'
        updateMessage.value = `You're on the latest version (v${r.version})`
        break
      case 'unsupported':
        updateLabel.value = 'See Releases'
        updateMessage.value = 'Auto-update is unavailable on macOS (unsigned build) — download new versions from the GitHub Releases page'
        break
      case 'dev':
        updateLabel.value = 'Dev build'
        updateMessage.value = 'Update checks only work in the packaged app'
        break
      default:
        updateLabel.value = 'Check failed'
        updateMessage.value = r.message || 'Could not reach the update server'
    }
  } catch {
    updateLabel.value = 'Check failed'
    updateMessage.value = 'Could not reach the update server'
  } finally {
    updateChecking.value = false
    // Downloading state persists (the OS dialog takes over); others revert
    if (!updateLabel.value.startsWith('↓')) {
      setTimeout(() => { updateLabel.value = 'Updates' }, 6000)
    }
  }
}
const loadInput = ref<HTMLInputElement | null>(null)

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

// Top-level generation mode. Loop/Arrangement drive GenerateForm (via genMode);
// Song drives SongForm + SongResult.
const mode = ref<'loop' | 'arrangement' | 'song'>('loop')
const genMode = computed<'loop' | 'arrangement'>(() => (mode.value === 'song' ? 'loop' : mode.value))
const MODE_LABELS = {
  loop: 'Loop',
  arrangement: 'Arrangement',
  song: 'Full Song',
}
const MODE_HINTS = {
  loop: 'One looping section — every part plays across every bar.',
  arrangement: 'A full arc — intro · verse · chorus · outro — from one bar count.',
  song: 'A complete song from a template; drag out each part.',
}

const songResult = ref<BuildSongResponse | null>(null)
const songLabel = ref('')

interface SongHistoryItem { result: BuildSongResponse; label: string }
const loadSongHistory = (): SongHistoryItem[] => {
  try { return JSON.parse(localStorage.getItem('genregrid_song_history') ?? '[]') } catch { return [] }
}
const songHistory = ref<SongHistoryItem[]>(loadSongHistory())
watch(songHistory, (val) => {
  localStorage.setItem('genregrid_song_history', JSON.stringify(val))
}, { deep: true })

// Restore the most recent song into view on load
if (songHistory.value.length) {
  songResult.value = songHistory.value[0].result
  songLabel.value = songHistory.value[0].label
}

// Reconcile the local song list with what's actually on disk: drop entries whose
// exports were cleaned up, and pick up songs this browser/profile hasn't seen
// (built elsewhere, or after clearing storage). Server truth wins on existence;
// local labels win on naming.
async function syncSongsFromServer() {
  try {
    const server = await listSongs()
    const serverIds = new Set(server.map(s => s.generation_id))
    const localIds = new Set(songHistory.value.map(i => i.result.generation_id))
    let merged = songHistory.value.filter(i => serverIds.has(i.result.generation_id))
    for (const s of [...server].reverse()) {
      if (!localIds.has(s.generation_id)) {
        merged = [{ result: s, label: `${s.template.replace('_', '–')} · ${s.style}` }, ...merged]
      }
    }
    songHistory.value = merged.slice(0, 20)
    if (!songResult.value && songHistory.value.length) {
      songResult.value = songHistory.value[0].result
      songLabel.value = songHistory.value[0].label
    } else if (songResult.value && !serverIds.has(songResult.value.generation_id)) {
      songResult.value = songHistory.value[0]?.result ?? null
      songLabel.value = songHistory.value[0]?.label ?? ''
    }
  } catch { /* backend unreachable — keep the local list */ }
}
onMounted(syncSongsFromServer)

function onSongBuilt(result: BuildSongResponse, label: string) {
  songResult.value = result
  songLabel.value = label
  songHistory.value = [{ result, label }, ...songHistory.value].slice(0, 20)
  prefetchSamplers(result.style)
  closeDrawer()   // reveal the freshly built song in the workspace
}

function loadSong(item: SongHistoryItem) {
  songResult.value = item.result
  songLabel.value = item.label
}

function deleteSong(genId: string) {
  songHistory.value = songHistory.value.filter(i => i.result.generation_id !== genId)
  if (songResult.value?.generation_id === genId) {
    const next = songHistory.value[0] ?? null
    songResult.value = next?.result ?? null
    songLabel.value = next?.label ?? ''
  }
}

function clearSongs() {
  songHistory.value = []
  songResult.value = null
  songLabel.value = ''
}

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

function deleteHistoryEntry(genId: string) {
  history.value = history.value.filter(r => r.generation_id !== genId)
}

function clearHistory() {
  // Keep pinned (starred) entries; drop the rest.
  history.value = history.value.filter(r => starredIds.value.has(r.generation_id))
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
  if (e.key === 'Escape') {
    if (drawer.value) { closeDrawer(); return }
    if (showHelp.value) { showHelp.value = false; return }
    if (showShortcuts.value) { showShortcuts.value = false; return }
  }
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
    showHelp.value = !showHelp.value
  }
}
onMounted(() => {
  window.addEventListener('keydown', onKeyDown)
})
onUnmounted(() => {
  window.removeEventListener('keydown', onKeyDown)
})

onMounted(async () => {
  try {
    styles.value = await fetchStyles()
    setStyleCatalog(styles.value)
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
    closeDrawer()   // reveal the new generation in the workspace
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
    setStyleCatalog(styles.value)
  } catch (e) {
    error.value = 'Could not reach backend — make sure uvicorn is running on port 8000.'
  }
}

function handleReplay(response: GenerateResponse) {
  replayData.value = null
  setTimeout(() => { replayData.value = response; openSetup() }, 0)
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
    closeDrawer()
  } catch (e: any) {
    error.value = e.message ?? 'Batch generation failed'
  } finally {
    batchLoading.value = false
  }
}

async function refreshStyles() {
  try {
    styles.value = await fetchStyles()
    setStyleCatalog(styles.value)
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
/* Shell: topbar / workspace / transport, pinned to the viewport. Only the
 * workspace scrolls. */
.app-shell {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  height: 100vh;
}

/* ── Topbar ─────────────────────────────────────────────────────────────── */
.topbar {
  display: flex;
  align-items: center;
  gap: var(--s2);
  height: 52px;
  padding: 0 var(--s4);
  border-bottom: 1px solid var(--line);
  background: var(--ground);
}
.brand {
  font-size: var(--t-title);
  font-weight: 650;
  letter-spacing: -.015em;
  margin-right: var(--s2);
}
.brand span { color: var(--accent); }
.spacer { flex: 1; }

.topbar-active { color: var(--accent); background: var(--accent-wash); }
.topbar-error { color: var(--bad); }

/* ── Workspace ──────────────────────────────────────────────────────────── */
.workspace { overflow-y: auto; }
.workspace-inner {
  max-width: 1080px;
  margin: 0 auto;
  padding: 0 var(--s5) var(--s7);
}

/* ═══ Drawers ═══════════════════════════════════════════════════════════ */
.scrim {
  position: fixed; inset: 0; z-index: 40;
  background: color-mix(in srgb, var(--sunken) 62%, transparent);
  backdrop-filter: blur(3px);
  opacity: 0; pointer-events: none;
  transition: opacity .18s;
}
.scrim.open { opacity: 1; pointer-events: auto; }

.sheet {
  position: fixed; z-index: 50;
  background: var(--raised);
  border: 1px solid var(--line);
  box-shadow: var(--shadow-lift);
  display: flex; flex-direction: column;
  transition: transform .22s cubic-bezier(.32,.72,0,1), opacity .18s;
}

/* Horizontal centering and the slide-in are folded into ONE transform. Using
 * the standalone `translate` property for centering alongside a `transform`
 * animation dropped the centering in the packaged Electron build, throwing the
 * sheet off the right edge. */
.sheet-top {
  top: 0; left: 50%;
  width: min(1060px, calc(100vw - 32px));
  max-width: 100%;
  max-height: min(86vh, 780px);
  border-top: none;
  border-radius: 0 0 var(--r-lg) var(--r-lg);
  transform: translate(-50%, -102%);
  opacity: 0;
}
.sheet-top.open { transform: translate(-50%, 0); opacity: 1; }

.sheet-right {
  top: 52px; bottom: 60px; right: 0;
  width: min(340px, 92vw);
  border-radius: var(--r-lg) 0 0 var(--r-lg);
  border-right: none;
  transform: translateX(102%);
  opacity: 0;
}
.sheet-right.open { transform: translateX(0); opacity: 1; }

.sheet-head {
  display: flex; align-items: center; gap: var(--s3);
  padding: var(--s4) var(--s5);
  border-bottom: 1px solid var(--line);
  flex-shrink: 0;
}
.sheet-title { font-size: var(--t-title); font-weight: 620; letter-spacing: -.015em; }
.sheet-hint { font-size: var(--t-meta); color: var(--ink-faint); }
/* No bottom padding: the setup forms' sticky action bar supplies the bottom
 * spacing and pins flush to the scroll-area edge, so content can't peek out
 * beneath it. Right-drawer content (Songs/Library) carries its own bottom pad. */
.sheet-body { overflow-y: auto; overflow-x: hidden; padding: var(--s5) var(--s5) 0; flex: 1; min-height: 0; }
.sheet-right .sheet-body { padding-bottom: var(--s5); }
.sheet-foot {
  display: flex; align-items: center; gap: var(--s2);
  padding: var(--s3) var(--s5);
  border-top: 1px solid var(--line);
  flex-shrink: 0;
}
.sheet-foot .eyebrow { margin-right: auto; }
.clear-btn { color: var(--ink-dim); }
.clear-btn:hover { color: var(--bad); }

/* ── Library / Songs rail ───────────────────────────────────────────────── */
.rail-empty { font-size: var(--t-meta); color: var(--ink-faint); line-height: 1.6; padding: var(--s3) 0; }
.song-list { display: flex; flex-direction: column; gap: var(--s2); }
.song-item {
  position: relative;
  display: flex; flex-direction: column; gap: 2px;
  padding: var(--s3) var(--s5) var(--s3) var(--s3);
  border: 1px solid var(--line);
  border-left: 2px solid transparent;
  border-radius: var(--r-md);
  background: var(--ground);
  cursor: pointer; text-align: left;
  transition: border-color .14s, background .14s;
}
.song-item:hover { border-color: var(--ink-faint); }
.song-item[aria-current="true"] { border-color: var(--line); border-left-color: var(--accent); background: var(--accent-wash); }
.si-label { font-size: var(--t-body); font-weight: 550; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.si-meta { font-size: var(--t-micro); color: var(--ink-dim); }
.si-del {
  position: absolute; top: var(--s2); right: var(--s2);
  width: 22px; height: 22px;
  display: grid; place-items: center;
  background: none; border: none; color: var(--ink-faint);
  font-size: 11px; cursor: pointer; border-radius: var(--r-sm);
  opacity: 0; transition: opacity .14s, color .14s, background .14s;
}
.song-item:hover .si-del { opacity: 1; }
.si-del:hover { color: var(--bad); background: var(--sunken); }

/* ── Progress / error rows (inside setup drawer) ────────────────────────── */
.progress-row { display: flex; align-items: center; gap: var(--s2); font-size: var(--t-meta); color: var(--accent); margin-top: var(--s3); }
@keyframes dot-blink { 0%, 80%, 100% { opacity: 0.2; } 40% { opacity: 1; } }
.progress-dots span { animation: dot-blink 1.4s infinite; }
.progress-dots span:nth-child(2) { animation-delay: 0.2s; }
.progress-dots span:nth-child(3) { animation-delay: 0.4s; }
.error-row { display: flex; align-items: center; gap: var(--s3); margin-top: var(--s3); }

/* ── Shortcuts modal ────────────────────────────────────────────────────── */
.shortcuts-overlay {
  position: fixed; inset: 0; z-index: 60;
  background: color-mix(in srgb, var(--sunken) 70%, transparent);
  backdrop-filter: blur(3px);
  display: flex; align-items: center; justify-content: center;
}
.shortcuts-modal {
  background: var(--raised);
  border: 1px solid var(--line);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-lift);
  padding: var(--s4) var(--s5);
  min-width: 300px;
}
.shortcuts-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--s3); }
.shortcuts-title { font-size: var(--t-title); font-weight: 620; letter-spacing: -.01em; }
.shortcuts-table { border-collapse: collapse; width: 100%; }
.shortcut-key {
  font-family: var(--f-mono);
  font-size: var(--t-meta);
  color: var(--accent);
  background: var(--sunken);
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  padding: 0.2rem 0.5rem;
  white-space: nowrap;
}
.shortcut-desc { font-size: var(--t-meta); color: var(--ink-dim); padding-left: var(--s4); }
.shortcut-section {
  padding: var(--s3) 0 var(--s1);
  font-size: var(--t-micro);
  font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em;
  color: var(--ink-faint);
  border-bottom: 1px solid var(--line);
}
.shortcuts-table tr { height: 2rem; }

/* ── Mode picker (top of the Setup drawer) ──────────────────────────────── */
.mode-picker {
  display: flex; flex-direction: column; gap: var(--s3);
  margin-bottom: var(--s5);
  padding-bottom: var(--s5);
  border-bottom: 1px solid var(--line);
}
.mode-picker-label { font-size: var(--t-body); font-weight: 600; color: var(--ink); }
.mode-cards { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--s2); }
.mode-card {
  display: flex; flex-direction: column; gap: 3px; align-items: flex-start;
  text-align: left; padding: var(--s3);
  border: 1px solid var(--line); border-radius: var(--r-md);
  background: var(--ground); cursor: pointer;
  transition: border-color .14s, background .14s;
}
.mode-card:hover { border-color: var(--ink-faint); }
.mode-card.active { border-color: var(--accent); background: var(--accent-wash); }
.mc-title { font-size: var(--t-body); font-weight: 600; color: var(--ink); }
.mode-card.active .mc-title { color: var(--accent); }
.mc-desc { font-size: var(--t-meta); color: var(--ink-dim); line-height: 1.35; }

@media (max-width: 860px) {
  .mode-cards { grid-template-columns: 1fr; }
}
@media (prefers-reduced-motion: reduce) {
  .sheet, .scrim { transition-duration: .01ms; }
}
</style>
