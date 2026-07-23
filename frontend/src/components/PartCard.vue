<!--
  GenreGrid — a style-based MIDI generator.
  Copyright (C) 2026 Tw Dover

  This program is free software: you can redistribute it and/or modify it under
  the terms of the GNU General Public License v3 or (at your option) any later
  version. Distributed WITHOUT ANY WARRANTY. See <https://www.gnu.org/licenses/>.
-->
<template>
  <div class="part-track" :class="{ playing, expired }">
    <span class="part-name" :title="instLabel ? `${file.part} — played by ${instLabel}` : file.part">
      <!-- Chords and melody show role + instrument (which line is which isn't
           obvious from the instrument alone); other roles are self-evident
           from their instrument (a bass is the bass) and stay one line. -->
      <template v-if="instLabel && showRole">
        <span class="pn-role">{{ file.part }}</span>
        <span class="pn-inst">{{ instLabel }}</span>
      </template>
      <template v-else>{{ instLabel ?? file.part }}</template>
    </span>

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
      <button v-if="rollable" class="icon-btn roll-btn" :disabled="regenLoading || locked" @click="$emit('roll', file.part)" :title="locked ? 'Locked — unlock to roll' : 'Roll 3 variations to compare and keep one'">×3</button>
      <button v-if="hasUndo" class="icon-btn" @click="$emit('undo')" title="Undo last regeneration">↩</button>
      <button v-if="!simple || lockable" class="icon-btn lock-btn" :class="{ locked }" @click="$emit('toggle-lock', file.part)" :title="locked ? 'Unlock part' : 'Lock part (keeps it when re-rolling sections)'">
        {{ locked ? '🔒' : '🔓' }}
      </button>
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
        v-if="midiData"
        class="save-btn"
        :disabled="renderingWav"
        @click="exportWav"
        :title="wavError || 'Render and download as WAV — see the ⬇ header button for progress from anywhere'"
      >
        <span v-if="renderingWav">{{ Math.round(wavProgress * 100) }}%</span>
        <span v-else>↓ .wav</span>
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
import { errorMessage } from '../utils/errors'
import { downloadUrl, editPart } from '../services/api'
import { useMidiPlayer, type ParsedNote, type PlayerPart } from '../composables/useMidiPlayer'
import { useDownloadPrompt } from '../composables/useDownloadPrompt'
import { useToasts } from '../composables/useToasts'
import { useRenderQueue } from '../composables/useRenderQueue'
import { logError } from '../composables/useErrorLog'
import { instrumentLabel } from '../composables/useStyleCatalog'
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
  lockable?: boolean   // force-show the lock toggle even in simple (song-stem) mode
  rollable?: boolean   // show the "×3" roll-candidates button (song stems only)
  gain?: number   // mixer gain (1.0 = generated balance); undefined hides the slider
  editable?: boolean   // enable piano-roll note editing (song stems only)
}>()

const emit = defineEmits<{
  (e: 'regen', part: string): void
  (e: 'roll', part: string): void
  (e: 'toggle-lock', part: string): void
  (e: 'undo'): void
  (e: 'gain', part: string, gain: number): void
  (e: 'edited', part: string): void
}>()

const saving = ref(false)
const saved = ref(false)
const tempFilePath = ref<string | null>(null)
const expired = ref(false)   // backend export was cleaned up — file no longer on disk

const isElectron = typeof window !== 'undefined' && !!window.electronAPI

// File System Access API — available in Chrome/Edge, not in Firefox/Safari
const hasPicker = typeof window !== 'undefined' && 'showSaveFilePicker' in window

const { toggle, currentlyPlaying, isLoading, getMidiData, prefetchMidi, offlineRender } = useMidiPlayer()
const { promptFilename } = useDownloadPrompt()
const { toast } = useToasts()
const { startJob, updateProgress, completeJob, failJob } = useRenderQueue()
// Instrument identity: label the part by what plays it ("Alto Sax"), falling
// back to the role name for styles without instrumentation (custom styles).
const instLabel = computed(() => instrumentLabel(props.styleId, props.file.part))
// Roles whose instrument name alone doesn't say what the line IS in the song
const showRole = computed(() => props.file.part === 'chords' || props.file.part === 'melody')
const playing = computed(() => currentlyPlaying.value === props.file.url)
const midiData = computed(() => getMidiData(props.file.url))

function baseName(filename: string): string {
  return filename.replace(/\.[^.]+$/, '')
}

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
    emit('edited', props.file.part)   // hand-edited parts auto-lock so a section re-roll won't discard them
    await cacheTempFile(props.file.url)   // re-verify + refresh caches / drag temp file
  } catch (e) {
    // Keep the edits on screen; surface the failure via the button title.
    editError.value = errorMessage(e) ?? 'Save failed'
    logError('Save note edits', e)
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
    tempFilePath.value = await window.electronAPI!.saveTempFile(props.file.filename, data)
  } catch {
    tempFilePath.value = null
  }
}

onMounted(() => cacheTempFile(props.file.url))
watch(() => props.file.url, url => { tempFilePath.value = null; cacheTempFile(url) })

function onMouseDown(e: MouseEvent) {
  if (!isElectron || e.button !== 0 || !tempFilePath.value) return
  e.preventDefault()
  window.electronAPI!.startDrag(tempFilePath.value)
}

function onDragStart(e: DragEvent) {
  if (isElectron) {
    e.preventDefault()
    if (tempFilePath.value) window.electronAPI!.startDrag(tempFilePath.value)
    return
  }
  const url = downloadUrl(props.file.url)
  e.dataTransfer!.setData('DownloadURL', `audio/midi:${props.file.filename}:${url}`)
  e.dataTransfer!.effectAllowed = 'copy'
}

async function saveTo() {
  const name = await promptFilename(baseName(props.file.filename), 'mid', `Save ${props.file.part}`)
  if (name === null) return   // cancelled
  saving.value = true
  try {
    const res = await fetch(downloadUrl(props.file.url))
    const buf = await res.arrayBuffer()
    const filename = `${name}.mid`

    if (hasPicker) {
      // Let the user pick the exact save location (e.g. their DAW project folder)
      const handle = await window.showSaveFilePicker!({
        suggestedName: filename,
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
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
    }

    saved.value = true
    setTimeout(() => { saved.value = false }, 2000)
  } catch (e) {
    // AbortError = user cancelled the picker — not an error
    if ((e as { name?: string })?.name !== 'AbortError') logError('Save part to disk', e)
  } finally {
    saving.value = false
  }
}

// ── WAV export ────────────────────────────────────────────────────────────────
const renderingWav = ref(false)
const wavProgress = ref(0)
const wavError = ref('')

async function exportWav() {
  if (renderingWav.value) return
  const name = await promptFilename(baseName(props.file.filename), 'wav', `Export ${props.file.part} as WAV`)
  if (name === null) return   // cancelled
  renderingWav.value = true
  wavProgress.value = 0
  wavError.value = ''
  // Tracked in the shared render queue too, so progress/completion stay visible
  // even if this card is unmounted (e.g. switching mode tabs) before it finishes —
  // the render itself keeps running either way, only the local UI would vanish.
  const jobId = startJob(`${props.file.part} — ${baseName(props.file.filename)}`, `${name}.wav`)
  try {
    const duration = midiData.value?.duration ?? 4
    // 'combined'/'song' stems render the full mix; any real part renders just itself.
    const channel = (props.file.part === 'combined' || props.file.part === 'song')
      ? 'all' : (props.file.part as PlayerPart)
    const blob = await offlineRender(props.file.url, props.styleId, duration, channel, v => {
      wavProgress.value = v
      updateProgress(jobId, v)
    })
    completeJob(jobId, blob)
    toast(`${props.file.part.replace('_', ' ')} exported as WAV`)
  } catch (e) {
    wavError.value = errorMessage(e) ?? 'WAV export failed'
    failJob(jobId, wavError.value)
    logError('WAV export', e)
    toast(wavError.value, 'error')
  } finally {
    renderingWav.value = false
  }
}
</script>

<style scoped>
/* A stem reads as a hairline row in a list, not a boxed card — the name and
 * instrument carry it, and the controls stay quiet until hovered. */
.part-track {
  display: flex;
  align-items: center;
  gap: var(--s4);
  background: transparent;
  border: 1px solid transparent;
  border-bottom: 1px solid var(--line);
  border-radius: 0;
  padding: var(--s3) var(--s2);
  min-width: 0;
  transition: background 0.14s;
}
.part-track:hover { background: var(--sunken); }

.part-track.playing {
  background: var(--accent-wash);
  border-bottom-color: var(--accent-edge);
}

.part-track.expired { opacity: 0.7; }

.expired-note {
  flex: 1;
  font-size: var(--t-meta);
  color: var(--bad);
  font-style: italic;
}

.part-name {
  width: 132px;
  flex-shrink: 0;
  line-height: 1.3;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
/* Single-line (self-evident) parts: the instrument name, calm and titled. */
.part-name { font-size: var(--t-title); font-weight: 550; color: var(--ink); letter-spacing: -.01em; text-transform: capitalize; }
.pn-role {
  font-size: var(--t-micro);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: var(--ink-faint);
}
.pn-inst {
  font-size: var(--t-meta);
  font-weight: 500;
  color: var(--ink-dim);
  text-transform: none;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.track-controls {
  display: flex;
  align-items: center;
  gap: var(--s1);
  flex-shrink: 0;
}

.icon-btn {
  width: 30px;
  height: 30px;
  flex-shrink: 0;
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--r-sm);
  color: var(--ink-dim);
  font-size: 0.85rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.14s, color 0.14s, border-color 0.14s;
}
.icon-btn:hover:not(:disabled) { background: var(--surface-hover); color: var(--ink); }
.icon-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.playing .icon-btn:first-child { background: var(--accent); border-color: var(--accent); color: var(--accent-ink); }
.lock-btn { font-size: 0.75rem; }
.roll-btn { font-size: 0.68rem; font-weight: 700; }
.lock-btn.locked { background: var(--accent-wash); border-color: var(--accent-edge); color: var(--accent); }

.drag-handle {
  width: 30px;
  height: 30px;
  flex-shrink: 0;
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--r-sm);
  color: var(--ink-faint);
  font-size: 1rem;
  cursor: grab;
  display: flex;
  align-items: center;
  justify-content: center;
  user-select: none;
  transition: background 0.14s, color 0.14s;
}
.drag-handle:hover { background: var(--surface-hover); color: var(--ink); }
.drag-handle:active { cursor: grabbing; }
.drag-handle:not(.drag-ready) { opacity: 0.4; cursor: wait; }

.save-btn {
  height: 30px;
  background: transparent;
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  color: var(--ink-dim);
  font-size: var(--t-meta);
  cursor: pointer;
  padding: 0 var(--s2);
  white-space: nowrap;
  transition: background 0.14s, color 0.14s, border-color 0.14s;
}
.save-btn:hover:not(:disabled) { border-color: var(--ink-faint); color: var(--ink); }
.save-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.edit-save-btn {
  border-color: var(--accent-edge);
  background: var(--accent-wash);
  color: var(--accent);
}

.gain-slider {
  width: 72px;
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
  background: var(--sunken);
  border-radius: var(--r-sm);
}
</style>
