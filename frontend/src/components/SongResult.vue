<!--
  GenreGrid — a style-based MIDI generator.
  Copyright (C) 2026 Tw Dover

  This program is free software: you can redistribute it and/or modify it under
  the terms of the GNU General Public License v3 or (at your option) any later
  version. Distributed WITHOUT ANY WARRANTY. See <https://www.gnu.org/licenses/>.
-->
<template>
  <div class="song-result">
    <div v-if="!result" class="sr-empty">
      <span class="sr-empty-icon">♫</span>
      <span>Build a full song to see its timeline and draggable parts.</span>
    </div>

    <template v-else>
      <!-- Header + whole-song actions -->
      <div class="sr-header">
        <div class="sr-title-block">
          <span class="sr-title">{{ label }}</span>
          <span class="sr-meta">{{ result.total_bars }} bars · {{ result.bpm }} BPM · {{ result.key }}</span>
        </div>
        <div class="sr-actions">
          <button class="sr-play-btn" :class="{ playing: isPlaying }" @click="togglePlay">
            {{ isPlaying ? '■ Stop' : '▶ Play song' }}
          </button>
          <button class="sr-dl-btn" @click="download">↓ .mid</button>
          <button class="sr-dl-btn" :disabled="renderingWav" @click="exportSongWav" :title="wavError || 'Render and download the full song as WAV — see the ⬇ header button for progress from anywhere'">
            <span v-if="renderingWav">{{ Math.round(wavProgress * 100) }}%</span>
            <span v-else>↓ .wav</span>
          </button>
          <div class="sr-history">
            <button class="sr-dl-btn" @click="toggleHistory" title="Restore an earlier version of this song">⟲ History</button>
            <div v-if="historyOpen" class="sr-history-menu">
              <div v-if="!songVersions.length" class="sr-history-empty">No earlier versions yet — re-rolls create them</div>
              <button
                v-for="v in songVersions"
                :key="v.id"
                class="sr-history-item"
                :disabled="restoreLoading !== null"
                @click="onRestore(v.id)"
              >{{ restoreLoading === v.id ? 'Restoring…' : v.saved_at.replace('T', ' ') }}</button>
            </div>
          </div>
        </div>
      </div>

      <!-- Section timeline — click a block to play from there, ⟳ to re-roll it -->
      <div class="sr-timeline">
        <div
          v-for="(sec, i) in result.sections"
          :key="sec.name"
          class="sr-tl-block"
          :class="[`seg-${sec.section_type}`, { 'sr-tl-busy': sectionRegenLoading === i, 'sr-tl-playing': playingSectionIndex === i }]"
          :style="{ flex: sec.bars }"
          :title="`${sec.name} · ${sec.bars} bars${sec.quality != null ? ` · quality ${(sec.quality * 100).toFixed(0)}%` : ''} — click to play from here`"
          @click="seekToSection(sec)"
        >
          <span
            v-if="sec.quality != null"
            class="sr-tl-dot"
            :class="sec.quality >= 0.82 ? 'q-good' : sec.quality >= 0.7 ? 'q-ok' : 'q-weak'"
          />
          <span class="sr-tl-name">{{ sec.name }}</span>
          <button
            v-if="sec.section_type !== 'ending'"
            class="sr-tl-regen"
            :disabled="sectionRegenLoading !== null"
            :title="`Re-roll ${sec.name}`"
            @click.stop="onRegenSection(i)"
          >{{ sectionRegenLoading === i ? '…' : '⟳' }}</button>
        </div>
        <div v-if="playheadPct !== null" class="sr-playhead" :style="{ left: `${playheadPct}%` }" />
      </div>

      <!-- Draggable per-part stems -->
      <div class="sr-parts-label">Parts <span class="sr-hint">⟳ re-roll · drag ⠿ into your DAW · ↓ to save</span></div>
      <div v-if="regenError" class="sr-error">{{ regenError }}</div>
      <div class="sr-stems">
        <PartCard
          v-for="file in bustedStems"
          :key="file.part"
          :file="file"
          :styleId="result.style"
          :keyRoot="keyRoot"
          :scale="scale"
          :regenLoading="regenLoading === file.part"
          :hasUndo="undoable.has(file.part)"
          :simple="true"
          :editable="true"
          :gain="partGains[file.part] ?? 1.0"
          @regen="onRegen"
          @undo="onUndo(file.part)"
          @gain="onGain"
        />
      </div>

      <!-- Parts not in this build — one click generates and adds the stem -->
      <div v-if="missingParts.length" class="sr-add-row">
        <span class="sr-add-label">Add a part</span>
        <button
          v-for="p in missingParts"
          :key="p"
          class="sr-add-btn"
          :disabled="addLoading !== null"
          :title="`Generate ${p} for this song`"
          @click="onAdd(p)"
        >
          <span v-if="addLoading === p">…</span>
          <span v-else>＋ {{ p.replace('_', ' ') }}</span>
        </button>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue'
import type { BuildSongResponse, FileInfo } from '../types/midi'
import { downloadUrl, regenerateSongPart, regenerateSongSection, undoSongPart, listSongVersions, restoreSongVersion, setPartGain, type SongVersion } from '../services/api'
import { useMidiPlayer } from '../composables/useMidiPlayer'
import { useToasts } from '../composables/useToasts'
import { logError } from '../composables/useErrorLog'
import { useDownloadPrompt } from '../composables/useDownloadPrompt'
import { useRenderQueue } from '../composables/useRenderQueue'
import PartCard from './PartCard.vue'

const props = defineProps<{ result: BuildSongResponse | null; label: string }>()

const { toggle, stop: stopPlayer, currentlyPlaying, seek, positionSeconds, offlineRender } = useMidiPlayer()
const { toast } = useToasts()
const { promptFilename } = useDownloadPrompt()
const { startJob, updateProgress, completeJob, failJob } = useRenderQueue()
let songBlobUrl: string | null = null
const renderingWav = ref(false)
const wavProgress = ref(0)
const wavError = ref('')

// Cache-bust versions per part (and the song) after a regeneration.
const versions = reactive<Record<string, number>>({})
const regenLoading = ref<string | null>(null)
const regenError = ref<string | null>(null)
const undoable = reactive(new Set<string>())

// Every part the song builder can produce — parts absent from the build are
// offered as one-click "add" buttons under the stems.
const ALL_PARTS = ['chords', 'bass', 'melody', 'drums', 'arpeggio', 'pads', 'counter_melody']
// Stems generated after the build via "add a part" (the result prop is immutable)
const addedFiles = ref<FileInfo[]>([])
const addLoading = ref<string | null>(null)
watch(() => props.result?.generation_id, () => { addedFiles.value = [] })

const stemFiles = computed(() => [
  ...(props.result?.files ?? []).filter(f => f.part !== 'song'),
  ...addedFiles.value,
])
const missingParts = computed(() => {
  if (!props.result) return []
  const have = new Set(stemFiles.value.map(f => f.part))
  return ALL_PARTS.filter(p => !have.has(p))
})
const bustedStems = computed(() => stemFiles.value.map(f =>
  versions[f.part] ? { ...f, url: `${f.url}?v=${versions[f.part]}` } : f))
const keyRoot = computed(() => (props.result?.key ?? 'C').split(' ')[0])
const scale = computed(() => (props.result?.key ?? 'C minor').split(' ')[1] ?? 'minor')

const songFile = computed(() => props.result?.files.find(f => f.part === 'song') ?? null)
const songUrl = computed(() => {
  if (!songFile.value) return null
  return versions.song ? `${songFile.value.url}?v=${versions.song}` : songFile.value.url
})
const isPlaying = computed(() => songBlobUrl !== null && currentlyPlaying.value === songBlobUrl)

// ── Live playhead ────────────────────────────────────────────────────────────
// Playback position in bars, mirroring the piecewise tempo map used by
// seekToSection (choruses run 1.2% faster than the base tempo).
const playheadBar = computed<number | null>(() => {
  if (!props.result || !isPlaying.value) return null
  const bpm = props.result.bpm || 120
  let remaining = positionSeconds.value
  let bars = 0
  for (const s of props.result.sections) {
    const isChorus = s.section_type === 'chorus' || s.section_type === 'post_chorus'
    const secDur = s.bars * 4 * 60 / (isChorus ? bpm * 1.012 : bpm)
    if (remaining < secDur) return bars + (remaining / secDur) * s.bars
    remaining -= secDur
    bars += s.bars
  }
  return bars
})
const playheadPct = computed<number | null>(() => {
  if (playheadBar.value === null || !props.result?.total_bars) return null
  return Math.min(100, (playheadBar.value / props.result.total_bars) * 100)
})
const playingSectionIndex = computed(() => {
  if (playheadBar.value === null || !props.result) return -1
  let acc = 0
  for (let i = 0; i < props.result.sections.length; i++) {
    acc += props.result.sections[i].bars
    if (playheadBar.value < acc) return i
  }
  return -1
})

async function onRegen(part: string) {
  if (!props.result || regenLoading.value) return
  regenLoading.value = part
  regenError.value = null
  try {
    await regenerateSongPart({ generation_id: props.result.generation_id, part })
    const v = Date.now()
    versions[part] = v      // reload the stem card + piano roll
    versions.song = v       // and the whole-song playback
    undoable.add(part)
    toast(`Re-rolled ${part.replace('_', ' ')}`)
  } catch (e: any) {
    regenError.value = e.message ?? 'Regeneration failed'
    logError('Regenerate part', e)
    toast(regenError.value ?? 'Regeneration failed', 'error')
  } finally {
    regenLoading.value = null
  }
}

// ── Mixer ────────────────────────────────────────────────────────────────────
// Per-part gains (1.0 = generated balance), seeded from the song's persisted
// mixer state and updated optimistically as sliders move.
const partGains = reactive<Record<string, number>>({})
watch(() => props.result, (r) => {
  for (const k of Object.keys(partGains)) delete partGains[k]
  if (r?.mixer) Object.assign(partGains, r.mixer)
}, { immediate: true })

async function onGain(part: string, gain: number) {
  if (!props.result) return
  const prev = partGains[part] ?? 1.0
  partGains[part] = gain
  regenError.value = null
  try {
    await setPartGain({ generation_id: props.result.generation_id, part, gain })
    const v = Date.now()
    versions[part] = v
    versions.song = v
    toast(`${part.replace('_', ' ')} volume applied`)
  } catch (e: any) {
    partGains[part] = prev
    regenError.value = e.message ?? 'Volume change failed'
    logError('Set part gain', e)
    toast(regenError.value ?? 'Volume change failed', 'error')
  }
}

// ── Version history ──────────────────────────────────────────────────────────
const historyOpen = ref(false)
const songVersions = ref<SongVersion[]>([])
const restoreLoading = ref<string | null>(null)
watch(() => props.result?.generation_id, () => { historyOpen.value = false; songVersions.value = [] })

async function toggleHistory() {
  historyOpen.value = !historyOpen.value
  if (historyOpen.value && props.result) {
    songVersions.value = await listSongVersions(props.result.generation_id)
  }
}

async function onRestore(versionId: string) {
  if (!props.result || restoreLoading.value) return
  restoreLoading.value = versionId
  regenError.value = null
  try {
    const files = await restoreSongVersion({ generation_id: props.result.generation_id, version_id: versionId })
    const v = Date.now()
    for (const f of files) versions[f.part] = v
    versions.song = v
    // A restore may add back stems that were later removed, or drop added ones —
    // reflect the restored file set in the "added" list so the cards match disk.
    const restored = new Set(files.map(f => f.part))
    addedFiles.value = addedFiles.value.filter(f => restored.has(f.part))
    historyOpen.value = false
    songVersions.value = await listSongVersions(props.result.generation_id)
    toast('Version restored')
  } catch (e: any) {
    regenError.value = e.message ?? 'Restore failed'
    logError('Restore song version', e)
    toast(regenError.value ?? 'Restore failed', 'error')
  } finally {
    restoreLoading.value = null
  }
}

const sectionRegenLoading = ref<number | null>(null)

async function onRegenSection(index: number) {
  if (!props.result || sectionRegenLoading.value !== null) return
  sectionRegenLoading.value = index
  regenError.value = null
  try {
    const files = await regenerateSongSection({
      generation_id: props.result.generation_id, section_index: index,
    })
    // Every stem may have been rewritten (theme/motif ripple) — bust them all.
    const v = Date.now()
    for (const f of files) versions[f.part] = v
    versions.song = v
    for (const f of files) if (f.part !== 'song') undoable.add(f.part)
    toast(`Re-rolled ${props.result.sections[index]?.name ?? 'section'}`)
  } catch (e: any) {
    regenError.value = e.message ?? 'Section regeneration failed'
    logError('Regenerate song section', e)
    toast(regenError.value ?? 'Section regeneration failed', 'error')
  } finally {
    sectionRegenLoading.value = null
  }
}

async function seekToSection(sec: { start_bar: number }) {
  if (!props.result) return
  // Piecewise beat→seconds mirroring the backend tempo map: choruses run 1.2%
  // faster than the base tempo, so a flat conversion drifts on long songs.
  const bpm = props.result.bpm || 120
  let seconds = 0
  for (const s of props.result.sections) {
    if (s.start_bar >= sec.start_bar) break
    const isChorus = s.section_type === 'chorus' || s.section_type === 'post_chorus'
    seconds += s.bars * 4 * 60 / (isChorus ? bpm * 1.012 : bpm)
  }
  if (!isPlaying.value) await togglePlay()
  seek(seconds)
}

async function onAdd(part: string) {
  if (!props.result || addLoading.value) return
  addLoading.value = part
  regenError.value = null
  try {
    const fi = await regenerateSongPart({ generation_id: props.result.generation_id, part })
    addedFiles.value = [...addedFiles.value, fi]
    const v = Date.now()
    versions[part] = v
    versions.song = v   // song.mid was rebuilt with the new stem
    toast(`Added ${part.replace('_', ' ')}`)
  } catch (e: any) {
    regenError.value = e.message ?? `Could not add ${part}`
    logError('Add song part', e)
    toast(regenError.value ?? `Could not add ${part}`, 'error')
  } finally {
    addLoading.value = null
  }
}

async function onUndo(part: string) {
  if (!props.result) return
  regenError.value = null
  try {
    await undoSongPart({ generation_id: props.result.generation_id, part })
    const v = Date.now()
    versions[part] = v
    versions.song = v
    undoable.delete(part)   // one level of undo
  } catch (e: any) {
    regenError.value = e.message ?? 'Undo failed'
    logError('Undo song part', e)
  }
}

async function togglePlay() {
  if (isPlaying.value) { stopPlayer(); return }
  if (!songUrl.value) return
  try {
    const res = await fetch(downloadUrl(songUrl.value))
    const blob = await res.blob()
    if (songBlobUrl) URL.revokeObjectURL(songBlobUrl)
    songBlobUrl = URL.createObjectURL(blob)
    await toggle(songBlobUrl, props.result?.style, props.label)
  } catch { /* playback failure is non-fatal */ }
}

async function download() {
  if (!songFile.value || !props.result) return
  const defaultName = `${props.result.style}_song_${props.result.generation_id.slice(0, 8)}`
  const name = await promptFilename(defaultName, 'mid', 'Save song')
  if (name === null) return   // cancelled
  const a = document.createElement('a')
  a.href = downloadUrl(songFile.value.url)
  a.download = `${name}.mid`
  a.click()
}

async function exportSongWav() {
  if (!songFile.value || !props.result || renderingWav.value) return
  const defaultName = `${props.result.style}_song_${props.result.generation_id.slice(0, 8)}`
  const name = await promptFilename(defaultName, 'wav', 'Export song as WAV')
  if (name === null) return   // cancelled
  renderingWav.value = true
  wavProgress.value = 0
  wavError.value = ''
  // Tracked in the shared render queue too — switching to another mode tab
  // unmounts this whole component, but the render keeps going regardless, and
  // the queue is what stays visible to show it finished (or failed).
  const jobId = startJob(`Song — ${defaultName}`, `${name}.wav`)
  try {
    // Nominal bar duration, padded: the chorus tempo push and closing
    // ritardando make the real playback slightly longer than a flat bpm
    // calculation, and offlineRender's buffer must cover the whole thing.
    const duration = (props.result.total_bars * 4 * 60 / props.result.bpm) * 1.05 + 2
    const blob = await offlineRender(songFile.value.url, props.result.style, duration, 'all', v => {
      wavProgress.value = v
      updateProgress(jobId, v)
    })
    completeJob(jobId, blob)
    toast('Song exported as WAV')
  } catch (e: any) {
    wavError.value = e?.message ?? 'WAV export failed'
    failJob(jobId, wavError.value)
    logError('Song WAV export', e)
    toast(wavError.value, 'error')
  } finally {
    renderingWav.value = false
  }
}
</script>

<style scoped>
.song-result { display: flex; flex-direction: column; gap: 0.75rem; }

.sr-empty {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 0.6rem; padding: 3rem 1rem; text-align: center;
  color: var(--text-faint); font-size: 0.8rem;
  border: 1px dashed var(--surface); border-radius: 10px;
}
.sr-empty-icon { font-size: 1.8rem; color: var(--seg-intro); }

.sr-header { display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; }
.sr-title-block { display: flex; flex-direction: column; gap: 0.15rem; min-width: 0; }
.sr-title { font-size: 0.9rem; font-weight: 600; color: var(--text); }
.sr-meta { font-size: 0.7rem; font-family: monospace; color: var(--text-dim); }

.sr-actions { display: flex; gap: 0.5rem; flex-shrink: 0; }
.sr-play-btn {
  font-size: 0.75rem; padding: 0.35rem 0.8rem; background: var(--accent-surface);
  border: 1px solid color-mix(in srgb, var(--accent) 27%, transparent); border-radius: 5px; color: var(--accent); cursor: pointer;
  transition: background 0.15s;
}
.sr-play-btn:hover { background: var(--accent-surface-strong); }
.sr-play-btn.playing { background: var(--accent-surface-strong); border-color: var(--accent); }
.sr-dl-btn {
  font-size: 0.75rem; padding: 0.35rem 0.65rem; background: var(--panel-deep);
  border: 1px solid var(--surface); border-radius: 5px; color: var(--text-dim); cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.sr-dl-btn:hover { background: var(--surface); color: var(--text); }

/* Version history dropdown */
.sr-history { position: relative; }
.sr-history-menu {
  position: absolute; right: 0; top: calc(100% + 4px); z-index: 20;
  background: var(--panel); border: 1px solid var(--surface); border-radius: 6px;
  min-width: 190px; padding: 0.25rem; display: flex; flex-direction: column; gap: 2px;
  box-shadow: 0 6px 18px rgba(0,0,0,0.5);
}
.sr-history-empty { font-size: 0.65rem; color: var(--text-faint); padding: 0.35rem 0.5rem; }
.sr-history-item {
  font-size: 0.7rem; font-family: monospace; text-align: left;
  background: transparent; border: none; border-radius: 4px;
  color: var(--text-dim); cursor: pointer; padding: 0.3rem 0.5rem;
}
.sr-history-item:hover:not(:disabled) { background: var(--surface); color: var(--accent); }
.sr-history-item:disabled { opacity: 0.5; cursor: wait; }

/* Timeline */
.sr-timeline { position: relative; display: flex; height: 30px; border-radius: 5px; overflow: hidden; gap: 1px; background: var(--bg-deepest); }
.sr-playhead {
  position: absolute; top: 0; bottom: 0; width: 2px;
  background: var(--accent); box-shadow: 0 0 6px color-mix(in srgb, var(--accent) 60%, transparent);
  pointer-events: none; z-index: 2;
}
.sr-tl-block {
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 0.35rem; overflow: hidden; min-width: 0; gap: 0.2rem;
  transition: filter 0.15s;
  cursor: pointer;
}
.sr-tl-block:hover { filter: brightness(1.2); }
.sr-tl-block.sr-tl-busy { filter: brightness(0.7); cursor: wait; }
.sr-tl-block.sr-tl-playing { filter: brightness(1.3); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--accent) 53%, transparent); }
.sr-tl-name { font-size: 0.58rem; color: var(--seg-text-dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; }
.sr-tl-dot { width: 5px; height: 5px; border-radius: 50%; flex-shrink: 0; }
.q-good { background: var(--success); }
.q-ok   { background: var(--gold); }
.q-weak { background: var(--error); }
.sr-tl-regen {
  background: none; border: none; padding: 0; flex-shrink: 0;
  font-size: 0.6rem; line-height: 1; color: var(--seg-text-faint); cursor: pointer;
  opacity: 0; transition: opacity 0.15s, color 0.15s;
}
.sr-tl-block:hover .sr-tl-regen { opacity: 1; }
.sr-tl-regen:hover:not(:disabled) { color: var(--seg-text); }
.sr-tl-regen:disabled { cursor: wait; }

.sr-parts-label {
  font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-dim);
  display: flex; align-items: baseline; gap: 0.5rem;
}
.sr-hint { font-size: 0.65rem; text-transform: none; letter-spacing: 0; color: var(--text-faint); }

.sr-stems { display: flex; flex-direction: column; gap: 0.4rem; }

.sr-error { font-size: 0.72rem; color: var(--error); background: var(--error-surface); border-radius: 4px; padding: 0.3rem 0.5rem; }

/* "Add a part" ghost row */
.sr-add-row { display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap; }
.sr-add-label {
  font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-faint);
  flex-shrink: 0;
}
.sr-add-btn {
  font-size: 0.7rem; padding: 0.3rem 0.6rem;
  background: transparent; border: 1px dashed var(--surface); border-radius: 6px;
  color: var(--text-dim); cursor: pointer; transition: border-color 0.15s, color 0.15s;
}
.sr-add-btn:hover:not(:disabled) { border-color: color-mix(in srgb, var(--accent) 40%, transparent); color: var(--accent); }
.sr-add-btn:disabled { opacity: 0.5; cursor: wait; }

/* Section type colors */
.seg-intro { background: var(--seg-intro); }
.seg-verse { background: var(--seg-verse); }
.seg-pre_chorus { background: var(--seg-pre_chorus); }
.seg-chorus { background: var(--seg-chorus); }
.seg-post_chorus { background: var(--seg-post_chorus); }
.seg-bridge { background: var(--seg-bridge); }
.seg-instrumental_solo { background: var(--seg-instrumental_solo); }
.seg-outro { background: var(--seg-outro); }
.seg-ending { background: var(--seg-ending); }
</style>
