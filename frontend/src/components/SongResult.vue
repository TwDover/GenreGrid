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

      <!-- Section timeline -->
      <div class="sr-timeline">
        <div
          v-for="sec in result.sections"
          :key="sec.name"
          class="sr-tl-block"
          :class="`seg-${sec.section_type}`"
          :style="{ flex: sec.bars }"
          :title="`${sec.name} · ${sec.bars} bars`"
        >
          <span class="sr-tl-name">{{ sec.name }}</span>
          <span class="sr-tl-bars">{{ sec.bars }}b</span>
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
          :simple="true"
          @regen="onRegen"
        />
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed } from 'vue'
import type { BuildSongResponse } from '../types/midi'
import { downloadUrl, regenerateSongPart } from '../services/api'
import { useMidiPlayer } from '../composables/useMidiPlayer'
import PartCard from './PartCard.vue'

const props = defineProps<{ result: BuildSongResponse | null; label: string }>()

const { toggle, stop: stopPlayer, currentlyPlaying } = useMidiPlayer()
let songBlobUrl: string | null = null

// Cache-bust versions per part (and the song) after a regeneration.
const versions = reactive<Record<string, number>>({})
const regenLoading = ref<string | null>(null)
const regenError = ref<string | null>(null)

const stemFiles = computed(() => (props.result?.files ?? []).filter(f => f.part !== 'song'))
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
  } catch (e: any) {
    regenError.value = e.message ?? 'Regeneration failed'
  } finally {
    regenLoading.value = null
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
}
.sr-tl-block:hover { filter: brightness(1.2); }
.sr-tl-name { font-size: 0.58rem; color: rgba(255,255,255,0.6); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; }
.sr-tl-bars { font-size: 0.52rem; font-family: monospace; color: rgba(255,255,255,0.3); flex-shrink: 0; }

.sr-parts-label {
  font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.06em; color: #4a7080;
  display: flex; align-items: baseline; gap: 0.5rem;
}
.sr-hint { font-size: 0.65rem; text-transform: none; letter-spacing: 0; color: #2a4550; }

.sr-stems { display: flex; flex-direction: column; gap: 0.4rem; }

.sr-error { font-size: 0.72rem; color: #f87171; background: #2a1010; border-radius: 4px; padding: 0.3rem 0.5rem; }

/* Section type colors */
.seg-intro { background: #1a4060; }
.seg-verse { background: #1a5040; }
.seg-pre_chorus { background: #3a4a20; }
.seg-chorus { background: #005580; }
.seg-post_chorus { background: #204060; }
.seg-bridge { background: #502060; }
.seg-instrumental_solo { background: #603020; }
.seg-outro { background: #102030; }
</style>
