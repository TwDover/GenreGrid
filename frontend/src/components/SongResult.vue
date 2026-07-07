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
        </div>
      </div>

      <!-- Section timeline — click a block to play from there, ⟳ to re-roll it -->
      <div class="sr-timeline">
        <div
          v-for="(sec, i) in result.sections"
          :key="sec.name"
          class="sr-tl-block"
          :class="[`seg-${sec.section_type}`, { 'sr-tl-busy': sectionRegenLoading === i }]"
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
          @regen="onRegen"
          @undo="onUndo(file.part)"
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
import { downloadUrl, regenerateSongPart, regenerateSongSection, undoSongPart } from '../services/api'
import { useMidiPlayer } from '../composables/useMidiPlayer'
import PartCard from './PartCard.vue'

const props = defineProps<{ result: BuildSongResponse | null; label: string }>()

const { toggle, stop: stopPlayer, currentlyPlaying, seek } = useMidiPlayer()
let songBlobUrl: string | null = null

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
  } catch (e: any) {
    regenError.value = e.message ?? 'Regeneration failed'
  } finally {
    regenLoading.value = null
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
  } catch (e: any) {
    regenError.value = e.message ?? 'Section regeneration failed'
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
  } catch (e: any) {
    regenError.value = e.message ?? `Could not add ${part}`
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

function download() {
  if (!songFile.value) return
  const a = document.createElement('a')
  a.href = downloadUrl(songFile.value.url)
  a.download = `song_${props.result?.generation_id ?? 'export'}.mid`
  a.click()
}
</script>

<style scoped>
.song-result { display: flex; flex-direction: column; gap: 0.75rem; }

.sr-empty {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 0.6rem; padding: 3rem 1rem; text-align: center;
  color: #2a4550; font-size: 0.8rem;
  border: 1px dashed #0d2535; border-radius: 10px;
}
.sr-empty-icon { font-size: 1.8rem; color: #1a4060; }

.sr-header { display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; }
.sr-title-block { display: flex; flex-direction: column; gap: 0.15rem; min-width: 0; }
.sr-title { font-size: 0.9rem; font-weight: 600; color: #e0e0e8; }
.sr-meta { font-size: 0.7rem; font-family: monospace; color: #4a7080; }

.sr-actions { display: flex; gap: 0.5rem; flex-shrink: 0; }
.sr-play-btn {
  font-size: 0.75rem; padding: 0.35rem 0.8rem; background: #001e35;
  border: 1px solid #00c8ff44; border-radius: 5px; color: #00c8ff; cursor: pointer;
  transition: background 0.15s;
}
.sr-play-btn:hover { background: #003450; }
.sr-play-btn.playing { background: #003450; border-color: #00c8ff; }
.sr-dl-btn {
  font-size: 0.75rem; padding: 0.35rem 0.65rem; background: #040a0e;
  border: 1px solid #0d2535; border-radius: 5px; color: #4a7080; cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.sr-dl-btn:hover { background: #0d2535; color: #e0e0e8; }

/* Timeline */
.sr-timeline { display: flex; height: 30px; border-radius: 5px; overflow: hidden; gap: 1px; background: #020608; }
.sr-tl-block {
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 0.35rem; overflow: hidden; min-width: 0; gap: 0.2rem;
  transition: filter 0.15s;
  cursor: pointer;
}
.sr-tl-block:hover { filter: brightness(1.2); }
.sr-tl-block.sr-tl-busy { filter: brightness(0.7); cursor: wait; }
.sr-tl-name { font-size: 0.58rem; color: rgba(255,255,255,0.6); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; }
.sr-tl-dot { width: 5px; height: 5px; border-radius: 50%; flex-shrink: 0; }
.q-good { background: #4ade80; }
.q-ok   { background: #facc15; }
.q-weak { background: #f87171; }
.sr-tl-regen {
  background: none; border: none; padding: 0; flex-shrink: 0;
  font-size: 0.6rem; line-height: 1; color: rgba(255,255,255,0.35); cursor: pointer;
  opacity: 0; transition: opacity 0.15s, color 0.15s;
}
.sr-tl-block:hover .sr-tl-regen { opacity: 1; }
.sr-tl-regen:hover:not(:disabled) { color: #fff; }
.sr-tl-regen:disabled { cursor: wait; }

.sr-parts-label {
  font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.06em; color: #4a7080;
  display: flex; align-items: baseline; gap: 0.5rem;
}
.sr-hint { font-size: 0.65rem; text-transform: none; letter-spacing: 0; color: #2a4550; }

.sr-stems { display: flex; flex-direction: column; gap: 0.4rem; }

.sr-error { font-size: 0.72rem; color: #f87171; background: #2a1010; border-radius: 4px; padding: 0.3rem 0.5rem; }

/* "Add a part" ghost row */
.sr-add-row { display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap; }
.sr-add-label {
  font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.06em; color: #2a4550;
  flex-shrink: 0;
}
.sr-add-btn {
  font-size: 0.7rem; padding: 0.3rem 0.6rem;
  background: transparent; border: 1px dashed #0d2535; border-radius: 6px;
  color: #4a7080; cursor: pointer; transition: border-color 0.15s, color 0.15s;
}
.sr-add-btn:hover:not(:disabled) { border-color: #00c8ff66; color: #00c8ff; }
.sr-add-btn:disabled { opacity: 0.5; cursor: wait; }

/* Section type colors */
.seg-intro { background: #1a4060; }
.seg-verse { background: #1a5040; }
.seg-pre_chorus { background: #3a4a20; }
.seg-chorus { background: #005580; }
.seg-post_chorus { background: #204060; }
.seg-bridge { background: #502060; }
.seg-instrumental_solo { background: #603020; }
.seg-outro { background: #102030; }
.seg-ending { background: #0a1420; }
</style>
