<template>
  <div class="part-card" :class="{ playing }">
    <div class="part-header">
      <span class="part-name">{{ file.part }}</span>
      <span class="part-file">{{ file.filename }}</span>
    </div>
    <div class="card-actions">
      <button class="play-btn" :disabled="isLoading" @click="toggle(file.url, styleId)" :title="playing ? 'Stop' : 'Preview'">
        <span v-if="isLoading && !playing">...</span>
        <span v-else>{{ playing ? '■' : '▶' }}</span>
      </button>
      <button class="regen-btn" :disabled="regenLoading" @click="$emit('regen', file.part)" title="Regenerate this part">
        <span v-if="regenLoading">...</span>
        <span v-else>⟳</span>
      </button>
      <div
        class="drag-handle"
        :class="{ 'drag-ready': tempFilePath !== null }"
        draggable="true"
        @mousedown="onMouseDown"
        @dragstart="onDragStart"
        :title="isElectron ? (tempFilePath ? 'Drag into DAW' : 'Preparing…') : 'Drag into DAW (Chrome/Edge)'"
      >⠿</div>
      <button
        class="save-btn"
        :disabled="saving"
        @click="saveTo"
        :title="hasPicker ? 'Choose where to save — navigate to your DAW project folder' : 'Download .mid'"
      >
        <span v-if="saving">...</span>
        <span v-else-if="saved">✓</span>
        <span v-else>{{ hasPicker ? 'Save to…' : '↓ .mid' }}</span>
      </button>
    </div>
    <PianoRoll
      v-if="midiData"
      :notes="midiData.notes"
      :duration="midiData.duration"
      :playing="playing"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import type { FileInfo } from '../types/midi'
import { downloadUrl } from '../services/api'
import { useMidiPlayer } from '../composables/useMidiPlayer'
import PianoRoll from './PianoRoll.vue'

const props = defineProps<{
  file: FileInfo
  styleId?: string
  regenLoading?: boolean
}>()

defineEmits<{ (e: 'regen', part: string): void }>()

const saving = ref(false)
const saved = ref(false)
const tempFilePath = ref<string | null>(null)

const isElectron = typeof window !== 'undefined' && !!(window as any).electronAPI

// File System Access API — available in Chrome/Edge, not in Firefox/Safari
const hasPicker = typeof window !== 'undefined' && 'showSaveFilePicker' in window

const { toggle, currentlyPlaying, isLoading, getMidiData, prefetchMidi } = useMidiPlayer()
const playing = computed(() => currentlyPlaying.value === props.file.url)
const midiData = computed(() => getMidiData(props.file.url))

async function cacheTempFile(url: string) {
  prefetchMidi(url)
  if (!isElectron) return
  try {
    const buf = await fetch(downloadUrl(url)).then(r => r.arrayBuffer())
    const data = Array.from(new Uint8Array(buf))
    tempFilePath.value = await (window as any).electronAPI.saveTempFile(props.file.filename, data)
  } catch {
    tempFilePath.value = null
  }
}

onMounted(() => cacheTempFile(props.file.url))
watch(() => props.file.url, url => { tempFilePath.value = null; cacheTempFile(url) })

function onMouseDown(e: MouseEvent) {
  if (!isElectron || e.button !== 0 || !tempFilePath.value) return
  e.preventDefault()
  ;(window as any).electronAPI.startDrag(tempFilePath.value)
}

function onDragStart(e: DragEvent) {
  if (isElectron) {
    e.preventDefault()
    if (tempFilePath.value) (window as any).electronAPI.startDrag(tempFilePath.value)
    return
  }
  const url = downloadUrl(props.file.url)
  e.dataTransfer!.setData('DownloadURL', `audio/midi:${props.file.filename}:${url}`)
  e.dataTransfer!.effectAllowed = 'copy'
}

async function saveTo() {
  saving.value = true
  try {
    const res = await fetch(downloadUrl(props.file.url))
    const buf = await res.arrayBuffer()

    if (hasPicker) {
      // Let the user pick the exact save location (e.g. their DAW project folder)
      const handle = await (window as any).showSaveFilePicker({
        suggestedName: props.file.filename,
        types: [{ description: 'MIDI File', accept: { 'audio/midi': ['.mid', '.midi'] } }],
      })
      const writable = await handle.createWritable()
      await writable.write(buf)
      await writable.close()
    } else {
      // Fallback: standard browser download
      const blob = new Blob([buf], { type: 'audio/midi' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = props.file.filename
      a.click()
      URL.revokeObjectURL(url)
    }

    saved.value = true
    setTimeout(() => { saved.value = false }, 2000)
  } catch (e: any) {
    // AbortError = user cancelled the picker — not an error
    if (e?.name !== 'AbortError') console.error('Save failed', e)
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.card-actions {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}

.play-btn, .regen-btn {
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  background: #2a2a3e;
  border: 1px solid #3a3a54;
  border-radius: 6px;
  color: #a78bfa;
  font-size: 0.9rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s;
}
.play-btn:hover:not(:disabled), .regen-btn:hover:not(:disabled) { background: #3a3a54; }
.play-btn:disabled, .regen-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.regen-btn { font-size: 1rem; }

.drag-handle {
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  background: #2a2a3e;
  border: 1px solid #3a3a54;
  border-radius: 6px;
  color: #a78bfa;
  font-size: 1.1rem;
  cursor: grab;
  display: flex;
  align-items: center;
  justify-content: center;
  user-select: none;
  transition: background 0.15s;
}
.drag-handle:hover { background: #3a3a54; }
.drag-handle:active { cursor: grabbing; }
.drag-handle:not(.drag-ready) { opacity: 0.4; cursor: wait; }

.save-btn {
  flex: 1;
  height: 36px;
  background: #2a2a3e;
  border: 1px solid #3a3a54;
  border-radius: 6px;
  color: #a78bfa;
  font-size: 0.8rem;
  cursor: pointer;
  padding: 0 0.75rem;
  white-space: nowrap;
  transition: background 0.15s, border-color 0.15s, color 0.15s;
}
.save-btn:hover:not(:disabled) { background: #3a3a54; }
.save-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.playing .play-btn {
  background: #3b1f6e;
  border-color: #a78bfa;
}

.playing {
  border-color: #a78bfa;
}
</style>
