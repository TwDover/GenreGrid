<!--
  GenreGrid — a style-based MIDI generator.
  Copyright (C) 2026 Tw Dover

  This program is free software: you can redistribute it and/or modify it under
  the terms of the GNU General Public License v3 or (at your option) any later
  version. Distributed WITHOUT ANY WARRANTY. See <https://www.gnu.org/licenses/>.
-->
<template>
  <div class="part-track" :class="{ playing, expired }">
    <span class="part-name">{{ file.part }}</span>

    <div v-if="expired" class="expired-note" title="This export was cleaned up. Replay from history or regenerate to restore it.">⚠ expired — regenerate to restore</div>

    <div v-else class="track-controls">
      <button class="icon-btn" :disabled="isLoading && !playing" @click="toggle(file.url, styleId, file.part)" :title="playing ? 'Stop' : 'Preview'">
        <span v-if="isLoading && !playing">…</span>
        <span v-else>{{ playing ? '■' : '▶' }}</span>
      </button>
      <button class="icon-btn" :disabled="regenLoading || locked" @click="$emit('regen', file.part)" :title="locked ? 'Locked — unlock to regenerate' : 'Regenerate'">
        <span v-if="regenLoading">…</span>
        <span v-else>⟳</span>
      </button>
      <button v-if="hasUndo" class="icon-btn" @click="$emit('undo')" title="Undo last regeneration">↩</button>
      <template v-if="!simple">
        <button class="icon-btn lock-btn" :class="{ locked }" @click="$emit('toggle-lock', file.part)" :title="locked ? 'Unlock part' : 'Lock part (keeps it when regenerating others)'">
          {{ locked ? '🔒' : '🔓' }}
        </button>
      </template>
      <input
        v-if="gain !== undefined"
        type="range"
        class="gain-slider"
        min="0.2"
        max="1.6"
        step="0.05"
        :value="gain"
        :title="`Volume ${Math.round((gain ?? 1) * 100)}% — release to apply`"
        @change="$emit('gain', file.part, +($event.target as HTMLInputElement).value)"
      />
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
      <button
        v-if="editable && editDirty"
        class="save-btn edit-save-btn"
        :disabled="savingEdits"
        @click="saveEdits"
        :title="editError || 'Write note edits into the stem and rebuild song.mid'"
      >
        <span v-if="savingEdits">…</span>
        <span v-else>Save edits</span>
      </button>
    </div>

    <div class="track-roll">
      <PianoRoll
        v-if="midiData"
        ref="rollRef"
        :notes="midiData.notes"
        :duration="midiData.duration"
        :playing="playing"
        :keyRoot="keyRoot"
        :scale="scale"
        :editable="editable"
        :seconds-per-beat="secondsPerBeat"
        @notes-changed="onNotesChanged"
      />
      <div v-else class="roll-empty" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { Midi } from '@tonejs/midi'
import type { Header } from '@tonejs/midi'
import type { FileInfo } from '../types/midi'
import { downloadUrl, editPart } from '../services/api'
import { useMidiPlayer, type ParsedNote } from '../composables/useMidiPlayer'
import PianoRoll from './PianoRoll.vue'

const props = defineProps<{
  file: FileInfo
  styleId?: string
  regenLoading?: boolean
  locked?: boolean
  hasUndo?: boolean
  keyRoot?: string
  scale?: string
  simple?: boolean
  gain?: number   // mixer gain (1.0 = generated balance); undefined hides the slider
  editable?: boolean   // enable piano-roll note editing (song stems only)
}>()

defineEmits<{
  (e: 'regen', part: string): void
  (e: 'toggle-lock', part: string): void
  (e: 'undo'): void
  (e: 'gain', part: string, gain: number): void
}>()

const saving = ref(false)
const saved = ref(false)
const tempFilePath = ref<string | null>(null)
const expired = ref(false)   // backend export was cleaned up — file no longer on disk

const isElectron = typeof window !== 'undefined' && !!(window as any).electronAPI

// File System Access API — available in Chrome/Edge, not in Firefox/Safari
const hasPicker = typeof window !== 'undefined' && 'showSaveFilePicker' in window

const { toggle, currentlyPlaying, isLoading, getMidiData, prefetchMidi } = useMidiPlayer()
const playing = computed(() => currentlyPlaying.value === props.file.url)
const midiData = computed(() => getMidiData(props.file.url))

// ── Note editing (song stems) ────────────────────────────────────────────────
const rollRef = ref<InstanceType<typeof PianoRoll> | null>(null)
const editedNotes = ref<ParsedNote[] | null>(null)
const editDirty = ref(false)
const savingEdits = ref(false)
const editError = ref('')
const secondsPerBeat = ref(0.5)
let midiHeader: Header | null = null   // tempo map of the current file (seconds ↔ ticks)

function onNotesChanged(notes: ParsedNote[], dirty: boolean) {
  editedNotes.value = notes
  editDirty.value = dirty
  if (dirty) editError.value = ''
}

async function saveEdits() {
  const notes = editedNotes.value
  if (!notes || savingEdits.value) return
  savingEdits.value = true
  editError.value = ''
  try {
    // file.url format: /exports/{gen_id}/{part}.mid
    const segs = props.file.url.split('/').filter(Boolean)
    const genId = segs[segs.length - 2]
    if (!genId) throw new Error(`Cannot derive generation id from ${props.file.url}`)

    // The roll edits in seconds; the backend wants beats. The file's own tempo
    // map (header) makes the conversion exact even with chorus pushes and the
    // ending ritardando; fall back to the nominal tempo if parsing failed.
    const toBeats = (sec: number) =>
      midiHeader ? midiHeader.secondsToTicks(sec) / midiHeader.ppq : sec / secondsPerBeat.value
    const payload = notes.map(n => {
      const start = Math.max(0, toBeats(n.time))
      const end = toBeats(n.time + n.duration)
      return {
        pitch: Math.max(0, Math.min(127, Math.round(n.midi))),
        start: +start.toFixed(4),
        duration: +Math.max(0.01, end - start).toFixed(4),
        velocity: Math.max(1, Math.min(127, Math.round(n.velocity * 127))),
      }
    })

    await editPart({ generation_id: genId, part: props.file.part, notes: payload })
    editDirty.value = false
    editedNotes.value = null
    rollRef.value?.markSaved()
    await cacheTempFile(props.file.url)   // re-verify + refresh caches / drag temp file
  } catch (e: any) {
    // Keep the edits on screen; surface the failure via the button title.
    editError.value = e?.message ?? 'Save failed'
  } finally {
    savingEdits.value = false
  }
}

async function cacheTempFile(url: string) {
  expired.value = false
  // One GET verifies the export still exists (a cleaned-up file 404s) and, in
  // Electron, provides the bytes for the drag temp file. The /exports route is
  // GET-only, so we must not use HEAD here.
  let res: Response
  try {
    res = await fetch(downloadUrl(url))
  } catch {
    expired.value = true
    return
  }
  if (!res.ok) { expired.value = true; return }
  prefetchMidi(url)   // warm the piano-roll cache (served from the HTTP cache)
  let buf: ArrayBuffer | null = null
  if (isElectron || props.editable) {
    try { buf = await res.arrayBuffer() } catch { buf = null }
  }
  if (props.editable && buf) {
    // Keep the file's tempo header: seconds → beats conversion for note edits,
    // and the seconds-per-beat step size for the roll's arrow-key nudges.
    try {
      const midi = new Midi(buf)
      midiHeader = midi.header
      secondsPerBeat.value = 60 / (midi.header.tempos[0]?.bpm ?? 120)
    } catch {
      midiHeader = null
    }
  }
  if (!isElectron || !buf) return
  try {
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
  background: var(--panel);
  border: 1px solid var(--surface);
  border-radius: 8px;
  padding: 0.5rem 0.75rem;
  min-width: 0;
  transition: border-color 0.15s;
}

.part-track.playing {
  border-color: var(--accent);
}

.part-track.expired {
  border-color: var(--error-surface);
  opacity: 0.75;
}

.expired-note {
  flex: 1;
  font-size: 0.72rem;
  color: var(--error);
  font-style: italic;
}

.part-name {
  width: 52px;
  flex-shrink: 0;
  font-size: 0.65rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--accent);
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
  background: var(--surface);
  border: 1px solid var(--surface-hover);
  border-radius: 6px;
  color: var(--accent);
  font-size: 0.85rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s;
}
.icon-btn:hover:not(:disabled) { background: var(--surface-hover); }
.icon-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.playing .icon-btn:first-child { background: var(--accent-surface-strong); border-color: var(--accent); }
.lock-btn { font-size: 0.75rem; }
.lock-btn.locked { background: var(--accent-surface); border-color: color-mix(in srgb, var(--accent) 33%, transparent); }

.drag-handle {
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  background: var(--surface);
  border: 1px solid var(--surface-hover);
  border-radius: 6px;
  color: var(--accent);
  font-size: 1rem;
  cursor: grab;
  display: flex;
  align-items: center;
  justify-content: center;
  user-select: none;
  transition: background 0.15s;
}
.drag-handle:hover { background: var(--surface-hover); }
.drag-handle:active { cursor: grabbing; }
.drag-handle:not(.drag-ready) { opacity: 0.4; cursor: wait; }

.save-btn {
  height: 32px;
  background: var(--surface);
  border: 1px solid var(--surface-hover);
  border-radius: 6px;
  color: var(--accent);
  font-size: 0.75rem;
  cursor: pointer;
  padding: 0 0.6rem;
  white-space: nowrap;
  transition: background 0.15s;
}
.save-btn:hover:not(:disabled) { background: var(--surface-hover); }
.save-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.edit-save-btn {
  border-color: color-mix(in srgb, var(--accent) 53%, transparent);
  background: var(--accent-surface-strong);
}

.gain-slider {
  width: 64px;
  flex-shrink: 0;
  accent-color: var(--accent);
  cursor: pointer;
}

.track-roll {
  flex: 1;
  min-width: 0;
}

.roll-empty {
  height: 40px;
  background: var(--panel-deep);
  border-radius: 4px;
  opacity: 0.4;
}
</style>
