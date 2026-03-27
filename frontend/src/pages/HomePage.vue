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
        <p v-if="error" class="error-msg">{{ error }}</p>
      </section>

      <section class="export-section">
        <ExportPanel :history="history" @replay="handleReplay" @part-regenned="handlePartRegenned" />
      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import GenerateForm from '../components/GenerateForm.vue'
import ExportPanel from '../components/ExportPanel.vue'
import { fetchStyles, generate } from '../services/api'
import type { StyleInfo, GenerateRequest, GenerateResponse, FileInfo } from '../types/midi'
import { useMidiPlayer } from '../composables/useMidiPlayer'

const { volume, setVolume } = useMidiPlayer()

const styles = ref<StyleInfo[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const history = ref<GenerateResponse[]>([])
const replayData = ref<GenerateResponse | null>(null)

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
  } catch (e: any) {
    error.value = e.message ?? 'Unknown error'
  } finally {
    loading.value = false
  }
}

function handleReplay(response: GenerateResponse) {
  replayData.value = null          // reset first so the watcher fires even if same seed
  setTimeout(() => { replayData.value = response }, 0)
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
</style>
