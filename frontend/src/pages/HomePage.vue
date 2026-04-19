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
import { ref, watch, onMounted } from 'vue'
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

const loadHistory = (): GenerateResponse[] => {
  try {
    return JSON.parse(localStorage.getItem('genregrid_history') ?? '[]')
  } catch {
    return []
  }
}
const history = ref<GenerateResponse[]>(loadHistory())
const replayData = ref<GenerateResponse | null>(null)
const activePanel = ref<'history' | 'library'>('history')

watch(history, (val) => {
  localStorage.setItem('genregrid_history', JSON.stringify(val))
}, { immediate: false, deep: true })

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
  try {
    const t0 = Date.now()
    const result = await generate(form)
    result._elapsed = ((Date.now() - t0) / 1000).toFixed(1)
    history.value = [result, ...history.value].slice(0, 10)
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
</style>
