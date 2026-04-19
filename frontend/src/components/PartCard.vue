<template>
  <div class="part-track" :class="{ playing }">
    <span class="part-name">{{ file.part }}</span>

    <div class="track-controls">
      <button class="icon-btn" :disabled="isLoading && !playing" @click="toggle(file.url, styleId, file.part)" :title="playing ? 'Stop' : 'Preview'">
        <span v-if="isLoading && !playing">…</span>
        <span v-else>{{ playing ? '■' : '▶' }}</span>
      </button>
      <button class="icon-btn" :disabled="regenLoading || locked" @click="$emit('regen', file.part)" :title="locked ? 'Locked — unlock to regenerate' : 'Regenerate'">
        <span v-if="regenLoading">…</span>
        <span v-else>⟳</span>
      </button>
      <button v-if="hasUndo" class="icon-btn" @click="$emit('undo')" title="Undo last regeneration">↩</button>
      <button class="icon-btn lock-btn" :class="{ locked }" @click="$emit('toggle-lock', file.part)" :title="locked ? 'Unlock part' : 'Lock part (keeps it when regenerating others)'">
        {{ locked ? '🔒' : '🔓' }}
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
        :title="hasPicker ? 'Save to DAW project folder' : 'Download .mid'"
      >
        <span v-if="saving">…</span>
        <span v-else-if="saved">✓</span>
        <span v-else>{{ hasPicker ? 'Save to…' : '↓ .mid' }}</span>
      </button>
    </div>

    <div class="track-roll">
      <PianoRoll
        v-if="midiData"
        :notes="midiData.notes"
        :duration="midiData.duration"
        :playing="playing"
        :keyRoot="keyRoot"
        :scale="scale"
      />
      <div v-else class="roll-empty" />
    </div>
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
  locked?: boolean
  hasUndo?: boolean
  keyRoot?: string
  scale?: string
}>()

defineEmits<{
  (e: 'regen', part: string): void
  (e: 'toggle-lock', part: string): void
  (e: 'undo'): void
}>()

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
.part-track {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  background: #060f14;
  border: 1px solid #0d2535;
  border-radius: 8px;
  padding: 0.5rem 0.75rem;
  min-width: 0;
  transition: border-color 0.15s;
}

.part-track.playing {
  border-color: #00c8ff;
}

.part-name {
  width: 52px;
  flex-shrink: 0;
  font-size: 0.65rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #00c8ff;
}

.track-controls {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  flex-shrink: 0;
}

.icon-btn {
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  background: #0d2535;
  border: 1px solid #122f40;
  border-radius: 6px;
  color: #00c8ff;
  font-size: 0.85rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s;
}
.icon-btn:hover:not(:disabled) { background: #122f40; }
.icon-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.playing .icon-btn:first-child { background: #003450; border-color: #00c8ff; }
.lock-btn { font-size: 0.75rem; }
.lock-btn.locked { background: #001e35; border-color: #00c8ff55; }

.drag-handle {
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  background: #0d2535;
  border: 1px solid #122f40;
  border-radius: 6px;
  color: #00c8ff;
  font-size: 1rem;
  cursor: grab;
  display: flex;
  align-items: center;
  justify-content: center;
  user-select: none;
  transition: background 0.15s;
}
.drag-handle:hover { background: #122f40; }
.drag-handle:active { cursor: grabbing; }
.drag-handle:not(.drag-ready) { opacity: 0.4; cursor: wait; }

.save-btn {
  height: 32px;
  background: #0d2535;
  border: 1px solid #122f40;
  border-radius: 6px;
  color: #00c8ff;
  font-size: 0.75rem;
  cursor: pointer;
  padding: 0 0.6rem;
  white-space: nowrap;
  transition: background 0.15s;
}
.save-btn:hover:not(:disabled) { background: #122f40; }
.save-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.track-roll {
  flex: 1;
  min-width: 0;
}

.roll-empty {
  height: 40px;
  background: #040a0e;
  border-radius: 4px;
  opacity: 0.4;
}
</style>
