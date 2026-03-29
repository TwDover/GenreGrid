<template>
  <div class="home-page">
    <header class="app-header">
      <div class="header-title">
        <h1>GenreGrid</h1>
        <p class="subtitle">Style-based MIDI generator</p>
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
        <GenerateForm :styles="styles" :loading="loading" :replayData="replayData" @submit="handleGenerate" />
        <div v-if="error && !loading" class="error-row">
          <p class="error-msg">{{ error }}</p>
          <button class="retry-btn" @click="retryFetch">Retry</button>
        </div>
      </section>

      <section class="export-section">
        <div class="panel-tabs">
          <button class="panel-tab" :class="{ active: activePanel === 'history' }" @click="activePanel = 'history'">History</button>
          <button class="panel-tab" :class="{ active: activePanel === 'library' }" @click="activePanel = 'library'">Library</button>
        </div>
        <ExportPanel v-if="activePanel === 'history'" :history="history" @replay="handleReplay" @part-regenned="handlePartRegenned" />
        <LibraryPanel v-else :styles="styles" @replay="handleLibraryReplay" />
      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import GenerateForm from '../components/GenerateForm.vue'
import ExportPanel from '../components/ExportPanel.vue'
import LibraryPanel from '../components/LibraryPanel.vue'
import { fetchStyles, generate } from '../services/api'
import type { StyleInfo, GenerateRequest, GenerateResponse, FileInfo, LibraryEntry } from '../types/midi'
import { useMidiPlayer } from '../composables/useMidiPlayer'

const { volume, setVolume } = useMidiPlayer()

const styles = ref<StyleInfo[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const history = ref<GenerateResponse[]>([])
const replayData = ref<GenerateResponse | null>(null)
const activePanel = ref<'history' | 'library'>('history')

onMounted(async () => {
  try {
    styles.value = await fetchStyles()
  } catch (e) {
    error.value = 'Could not reach backend — make sure uvicorn is running on port 8000.'
  }
})

async function handleGenerate(form: GenerateRequest) {
  loading.value = true
  error.value = null
  try {
    const result = await generate(form)
    history.value = [result, ...history.value].slice(0, 10)
    activePanel.value = 'history'
  } catch (e: any) {
    error.value = e.message ?? 'Unknown error'
  } finally {
    loading.value = false
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
  background: #3a3a54;
  outline: none;
  cursor: pointer;
}

.vol-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #a78bfa;
  cursor: pointer;
}

.vol-slider::-moz-range-thumb {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #a78bfa;
  cursor: pointer;
  border: none;
}

.error-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.retry-btn {
  font-size: 0.75rem;
  padding: 0.2rem 0.6rem;
  background: #2a2a3e;
  border: 1px solid #3a3a54;
  border-radius: 4px;
  color: #8888a0;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
  white-space: nowrap;
}

.retry-btn:hover {
  background: #3a3a54;
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
  background: #1a1a24;
  border: 1px solid #2a2a3e;
  border-radius: 6px;
  color: #8888a0;
  cursor: pointer;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}

.panel-tab:hover { background: #22223a; color: #e0e0e8; }

.panel-tab.active {
  background: #2a1a4e;
  border-color: #a78bfa;
  color: #c4b5fd;
}
</style>
