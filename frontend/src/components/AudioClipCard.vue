<!--
  GenreGrid — a style-based MIDI generator.
  Copyright (C) 2026 Tw Dover

  This program is free software: you can redistribute it and/or modify it under
  the terms of the GNU General Public License v3 or (at your option) any later
  version. Distributed WITHOUT ANY WARRANTY. See <https://www.gnu.org/licenses/>.
-->
<template>
  <div class="audio-clip-card" :class="{ recording: mode === 'recording' }">
    <span class="ac-name">🎤 Audio</span>

    <template v-if="mode === 'recording'">
      <span class="ac-status">Recording…</span>
      <div class="ac-meter" title="Input level — if this never moves, the wrong device is likely selected">
        <div class="ac-meter-fill" :style="{ width: Math.round(level * 100) + '%' }" />
      </div>
      <button class="icon-btn" @click="stopAndReview" title="Stop recording">■ Stop</button>
    </template>

    <template v-else-if="mode === 'review'">
      <canvas ref="canvasRef" class="ac-waveform" width="240" height="40" />
      <button class="icon-btn" @click="previewTake" :title="previewing ? 'Stop preview' : 'Preview the take'">
        {{ previewing ? '■' : '▶' }}
      </button>
      <button class="save-btn" :disabled="saving" @click="save" title="Save this take">
        <span v-if="saving">…</span>
        <span v-else>✓ Save</span>
      </button>
      <button class="icon-btn" @click="discard" title="Discard this take">✕</button>
    </template>

    <template v-else-if="clip">
      <canvas ref="canvasRef" class="ac-waveform" width="240" height="40" />
      <span class="ac-placement">{{ placementLabel }}</span>
      <button class="icon-btn" @click="playSavedClip" :title="previewing ? 'Stop' : 'Preview'">
        {{ previewing ? '■' : '▶' }}
      </button>
      <button
        class="icon-btn mute-btn"
        :class="{ muted: audioClipMuted }"
        @click="toggleAudioClipMute"
        :title="audioClipMuted ? 'Unmute in the mix' : 'Mute in the mix'"
      >M</button>
      <select v-if="devices.length > 1" v-model="selectedDeviceId" class="ac-device-select" title="Input device to record with">
        <option v-for="(d, i) in devices" :key="d.deviceId" :value="d.deviceId">{{ d.label || `Microphone ${i + 1}` }}</option>
      </select>
      <button class="icon-btn" :disabled="arming" @click="armAndRecord" title="Re-record (replaces this take)">● Re-rec</button>
      <button class="icon-btn" :disabled="deleting" @click="deleteClip" title="Delete this take">🗑</button>
    </template>

    <template v-else>
      <select v-if="sections?.length" v-model.number="sectionIndex" class="ac-section-select" title="Which section to record into">
        <option v-for="(s, i) in sections" :key="i" :value="i">{{ s.name }} ({{ s.bars }} bars)</option>
      </select>
      <select v-if="devices.length > 1" v-model="selectedDeviceId" class="ac-device-select" title="Input device to record with">
        <option v-for="(d, i) in devices" :key="d.deviceId" :value="d.deviceId">{{ d.label || `Microphone ${i + 1}` }}</option>
      </select>
      <button class="icon-btn" :disabled="arming" @click="armAndRecord" title="Record a take from the microphone">
        <span v-if="arming">…</span>
        <span v-else>● Rec</span>
      </button>
    </template>

    <div v-if="error" class="ac-error">{{ error }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import * as Tone from 'tone'
import type { AudioClipInfo } from '../types/midi'
import type { EditorSection } from './PianoRollEditor.vue'
import { useAudioRecorder } from '../composables/useAudioRecorder'
import { useMidiPlayer } from '../composables/useMidiPlayer'
import { useMetronome } from '../composables/useMetronome'
import { saveAudioClip, deleteAudioClip, downloadUrl } from '../services/api'
import { encodeWav } from '../utils/wavEncoder'
import { waveformPeaks } from '../utils/audioClip'
import { errorMessage } from '../utils/errors'
import { logError } from '../composables/useErrorLog'

const props = defineProps<{
  generationId: string
  styleId?: string
  bpm: number
  clip: AudioClipInfo | null
  playbackUrl: string          // the combined song/loop MIDI to play along with while recording
  sections?: EditorSection[]   // song mode: pick which section to record into
  totalBars?: number           // loop mode fallback region (no sections) — the whole loop
}>()

const emit = defineEmits<{
  (e: 'saved', clip: AudioClipInfo): void
  (e: 'deleted'): void
}>()

const BEATS_PER_BAR = 4

const recorder = useAudioRecorder()
const { toggle, stop: stopPlayer, audioClipMuted, toggleAudioClipMute } = useMidiPlayer()
const { countIn: metroCountIn, setMeter: metroSetMeter } = useMetronome()

type Mode = 'idle' | 'recording' | 'review'
const mode = ref<Mode>('idle')
const sectionIndex = ref(0)
const arming = ref(false)
const saving = ref(false)
const deleting = ref(false)
const previewing = ref(false)
const error = ref('')
const canvasRef = ref<HTMLCanvasElement | null>(null)
const devices = ref<MediaDeviceInfo[]>([])
const selectedDeviceId = ref<string | undefined>(undefined)
const level = ref(0)

let takeBuffer: AudioBuffer | null = null
let pendingRegion: { start_bar: number; bars: number } | null = null
let autoStopTimer: ReturnType<typeof setTimeout> | null = null
let previewEl: HTMLAudioElement | null = null
let previewUrl: string | null = null
let levelTimer: ReturnType<typeof setInterval> | null = null

// Device labels are blank until mic permission has been granted at least once
// (browser privacy) — re-list right after a successful first open so the
// picker gets real names instead of "Microphone 1"/"Microphone 2" from then on.
onMounted(async () => {
  try { devices.value = await recorder.listInputDevices() } catch { /* picker just stays empty */ }
})

function startLevelMeter(): void {
  stopLevelMeter()
  levelTimer = setInterval(() => { level.value = recorder.getLevel() }, 100)
}
function stopLevelMeter(): void {
  if (levelTimer) { clearInterval(levelTimer); levelTimer = null }
  level.value = 0
}

const secPerBeat = computed(() => 60 / Math.max(1, props.bpm))
function regionSeconds(startBar: number, bars: number) {
  return { start: startBar * BEATS_PER_BAR * secPerBeat.value, dur: bars * BEATS_PER_BAR * secPerBeat.value }
}

function currentSelection(): { start_bar: number; bars: number } {
  if (props.sections?.length) {
    const s = props.sections[sectionIndex.value] ?? props.sections[0]
    return { start_bar: s.start_bar, bars: s.bars }
  }
  return { start_bar: 0, bars: Math.max(1, props.totalBars ?? 4) }
}

const placementLabel = computed(() => {
  if (!props.clip) return ''
  const s = props.sections?.find(s => s.start_bar === props.clip!.start_bar)
  return s ? s.name : `bar ${props.clip.start_bar + 1}, ${props.clip.bars} bars`
})

// ── Record ────────────────────────────────────────────────────────────────
async function armAndRecord() {
  if (arming.value || mode.value !== 'idle') return
  error.value = ''
  arming.value = true
  const region = currentSelection()
  const { start, dur } = regionSeconds(region.start_bar, region.bars)
  try {
    // Count-in reads the transport's current bpm; the song/loop hasn't loaded
    // into the player yet at this point, so it must be set explicitly.
    Tone.getTransport().bpm.value = props.bpm
    metroSetMeter(BEATS_PER_BAR, 4)
    await metroCountIn()
    await recorder.start(selectedDeviceId.value)
    mode.value = 'recording'
    startLevelMeter()
    // Labels are blank until permission is granted — now that it has been,
    // re-list so the picker shows real device names from here on.
    recorder.listInputDevices().then(d => { devices.value = d }).catch(() => {})
    // A loop region always repeats (useMidiPlayer.toggle's semantics) — the
    // auto-stop timer below ends the take after exactly one pass regardless.
    await toggle(props.playbackUrl, props.styleId, 'Recording', false, { start, end: start + dur })
    pendingRegion = region
    autoStopTimer = setTimeout(() => { void stopAndReview() }, Math.ceil(dur * 1000))
  } catch (e) {
    error.value = errorMessage(e) ?? 'Could not start recording'
    logError('Start audio recording', e)
    recorder.cancel()
    stopLevelMeter()
    mode.value = 'idle'
  } finally {
    arming.value = false
  }
}

async function stopAndReview() {
  if (mode.value !== 'recording' || !pendingRegion) return
  if (autoStopTimer) { clearTimeout(autoStopTimer); autoStopTimer = null }
  stopPlayer()
  stopLevelMeter()
  const { dur } = regionSeconds(pendingRegion.start_bar, pendingRegion.bars)
  try {
    const blob = await recorder.stop()
    takeBuffer = await recorder.decodeAndFit(blob, dur)
    mode.value = 'review'
    await nextTick()
    if (takeBuffer) drawWaveform(takeBuffer)
  } catch (e) {
    error.value = errorMessage(e) ?? 'Recording failed'
    logError('Stop audio recording', e)
    pendingRegion = null
    mode.value = 'idle'
  }
}

function discard() {
  stopPreview()
  takeBuffer = null
  pendingRegion = null
  mode.value = 'idle'
}

async function save() {
  if (!takeBuffer || !pendingRegion || saving.value) return
  saving.value = true
  error.value = ''
  try {
    const wav = encodeWav(takeBuffer)
    const info = await saveAudioClip({
      generation_id: props.generationId, start_bar: pendingRegion.start_bar, bars: pendingRegion.bars, file: wav,
    })
    emit('saved', info)
    stopPreview()
    takeBuffer = null
    pendingRegion = null
    mode.value = 'idle'
  } catch (e) {
    error.value = errorMessage(e) ?? 'Save failed'
    logError('Save audio clip', e)
  } finally {
    saving.value = false
  }
}

async function deleteClip() {
  if (!props.clip || deleting.value) return
  deleting.value = true
  error.value = ''
  try {
    await deleteAudioClip(props.generationId)
    stopPreview()
    emit('deleted')
  } catch (e) {
    error.value = errorMessage(e) ?? 'Delete failed'
    logError('Delete audio clip', e)
  } finally {
    deleting.value = false
  }
}

// ── Preview (a plain <audio> element — simplest path for a one-shot WAV;
//    the mix-graph integration for playback-alongside-the-song is separate) ──
function previewTake() {
  if (!takeBuffer) return
  if (previewing.value) { stopPreview(); return }
  if (previewUrl) URL.revokeObjectURL(previewUrl)
  previewUrl = URL.createObjectURL(encodeWav(takeBuffer))
  playPreviewUrl(previewUrl)
}
function playSavedClip() {
  if (!props.clip) return
  if (previewing.value) { stopPreview(); return }
  playPreviewUrl(downloadUrl(props.clip.url))
}
function playPreviewUrl(url: string) {
  stopPreview()
  previewEl = new Audio(url)
  previewEl.onended = () => { previewing.value = false }
  previewEl.play().catch(() => { previewing.value = false })
  previewing.value = true
}
function stopPreview() {
  previewEl?.pause()
  previewEl = null
  previewing.value = false
}

// ── Waveform (read-only — v1 has no trim/split editing) ──────────────────────
function drawWaveform(buffer: AudioBuffer) {
  const canvas = canvasRef.value
  const ctx = canvas?.getContext('2d')
  if (!canvas || !ctx) return
  const peaks = waveformPeaks(buffer, canvas.width)
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  ctx.fillStyle = 'currentColor'
  const mid = canvas.height / 2
  for (let i = 0; i < peaks.length; i++) {
    const h = Math.max(1, peaks[i] * mid)
    ctx.fillRect(i, mid - h, 1, h * 2)
  }
}

async function loadSavedWaveform() {
  if (!props.clip) return
  try {
    const res = await fetch(downloadUrl(props.clip.url))
    const arrayBuffer = await res.arrayBuffer()
    const ctx = Tone.getContext().rawContext as AudioContext
    const buffer = await ctx.decodeAudioData(arrayBuffer)
    await nextTick()
    drawWaveform(buffer)
  } catch {
    // The waveform is a visual nicety — a failed fetch/decode just leaves the canvas blank.
  }
}
watch(() => props.clip, c => { if (c) loadSavedWaveform() }, { immediate: true })

onUnmounted(() => {
  if (autoStopTimer) clearTimeout(autoStopTimer)
  if (mode.value === 'recording') recorder.cancel()
  stopLevelMeter()
  stopPreview()
  if (previewUrl) URL.revokeObjectURL(previewUrl)
})

defineExpose({ mode, armAndRecord, stopAndReview, discard, save, deleteClip })
</script>

<style scoped>
.audio-clip-card {
  display: flex;
  align-items: center;
  gap: var(--s4);
  border-bottom: 1px solid var(--line);
  padding: var(--s3) var(--s2);
  min-width: 0;
}
.audio-clip-card.recording { background: var(--error-surface); }
.ac-name { font-weight: 600; color: var(--text-soft); flex-shrink: 0; }
.ac-status { color: var(--text-dim); font-style: italic; }
.ac-waveform {
  height: 40px;
  width: 240px;
  max-width: 40vw;
  border-radius: var(--r-sm);
  background: var(--panel-alt);
}
.ac-placement { color: var(--text-dim); font-size: var(--t-meta); }
.ac-section-select { max-width: 12rem; }
.ac-device-select { max-width: 12rem; }
.ac-meter {
  width: 80px;
  height: 8px;
  border-radius: 4px;
  background: var(--panel-alt);
  overflow: hidden;
}
.ac-meter-fill {
  height: 100%;
  background: var(--accent);
  transition: width 0.1s linear;
}
.ac-error { color: var(--error); font-size: var(--t-meta); }

/* Matches PartCard.vue's .icon-btn / .save-btn — scoped styles don't cascade
   across components, so the shared look is duplicated rather than shared. */
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
}
.icon-btn:hover:not(:disabled) { background: var(--surface-hover); color: var(--ink); }
.icon-btn:disabled { opacity: 0.4; cursor: not-allowed; }

.save-btn {
  height: 30px;
  background: transparent;
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  color: var(--ink-dim);
  font-size: var(--t-meta);
  cursor: pointer;
  padding: 0 var(--s2);
}
.save-btn:hover:not(:disabled) { border-color: var(--ink-faint); color: var(--ink); }
.save-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.mute-btn { font-size: 0.7rem; font-weight: 700; }
.mute-btn.muted {
  background: var(--accent-wash);
  border-color: var(--accent-edge);
  color: var(--accent);
  text-decoration: line-through;
}
</style>
