<!--
  GenreGrid — a style-based MIDI generator.
  Copyright (C) 2026 Tw Dover

  This program is free software: you can redistribute it and/or modify it under
  the terms of the GNU General Public License v3 or (at your option) any later
  version. Distributed WITHOUT ANY WARRANTY. See <https://www.gnu.org/licenses/>.
-->
<template>
  <div class="arrange-panel">
    <div class="arrange-header">
      <span class="arrange-title">Arrangement</span>
      <span class="arrange-hint">Click "+ Arrange" on any generation to add it</span>
    </div>

    <!-- Visual timeline -->
    <div v-if="sections.length" class="arrange-timeline">
      <div
        v-for="(sec, i) in sections"
        :key="sec.uid"
        class="timeline-block"
        :style="{ flex: sec.bars * sec.repeat }"
        :class="{ 'tl-playing': isPlaying && currentSection === i }"
        :title="`${formatStyle(sec.style)} · ${sec.bars * sec.repeat} bars`"
      >
        <span class="tl-label">{{ formatStyle(sec.style) }}</span>
        <span class="tl-bars">{{ sec.bars * sec.repeat }}b</span>
      </div>
    </div>

    <!-- Section list -->
    <div class="arrange-sequence" v-if="sections.length">
      <div
        v-for="(sec, i) in sections"
        :key="sec.uid"
        class="arrange-section"
        :class="{ 'sec-playing': isPlaying && currentSection === i }"
      >
        <span class="sec-order">{{ i + 1 }}</span>
        <span class="sec-style">{{ formatStyle(sec.style) }}</span>
        <span class="sec-meta">{{ sec.key }} · {{ sec.bpm }}bpm · {{ sec.bars }}b</span>
        <div class="sec-repeat">
          <button class="rep-btn" @click="setRepeat(i, sec.repeat - 1)" :disabled="sec.repeat <= 1">−</button>
          <span class="rep-count">×{{ sec.repeat }}</span>
          <button class="rep-btn" @click="setRepeat(i, sec.repeat + 1)" :disabled="sec.repeat >= 8">+</button>
        </div>
        <div class="sec-actions">
          <button class="sec-btn" :disabled="i === 0" @click="moveUp(i)" title="Move up">↑</button>
          <button class="sec-btn" :disabled="i === sections.length - 1" @click="moveDown(i)" title="Move down">↓</button>
          <button class="sec-btn remove" @click="remove(i)" title="Remove">✕</button>
        </div>
      </div>
    </div>
    <div v-else class="arrange-empty">No sections yet — add them from your generations above</div>

    <div class="arrange-footer" v-if="sections.length">
      <span class="arrange-total">{{ totalBars }} bars total</span>
      <button class="arrange-play-btn" :class="{ playing: isPlaying }" :disabled="building" @click="togglePlayback">
        <span v-if="building">…</span>
        <span v-else-if="isPlaying">■ Stop</span>
        <span v-else>▶ Play</span>
      </button>
      <button class="arrange-dl-btn" :disabled="downloading || building" @click="downloadArrangement">
        {{ downloading ? 'Building…' : '↓ MIDI' }}
      </button>
    </div>
    <div v-if="error" class="arrange-error">{{ error }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onUnmounted } from 'vue'
import type { GenerateResponse } from '../types/midi'
import { errorMessage } from '../utils/errors'
import { arrangeDownload } from '../services/api'
import { useMidiPlayer } from '../composables/useMidiPlayer'

interface ArrangeSection {
  uid: string
  generation_id: string
  filename: string
  style: string
  key: string
  bpm: number
  bars: number
  repeat: number
}

const sections = ref<ArrangeSection[]>([])
const downloading = ref(false)
const building = ref(false)
const error = ref<string | null>(null)
let arrangeBlobUrl: string | null = null

const { toggle, stop: stopPlayer, currentlyPlaying } = useMidiPlayer()

const isPlaying = computed(() => arrangeBlobUrl !== null && currentlyPlaying.value === arrangeBlobUrl)

const totalBars = computed(() => sections.value.reduce((s, sec) => s + sec.bars * sec.repeat, 0))

// Estimate which section is currently playing based on Tone transport position
const currentSection = computed(() => {
  if (!isPlaying.value) return -1
  // Approximate — just highlight first section for now
  return 0
})

function addGeneration(response: GenerateResponse) {
  const combined = response.files.find(f => f.part === 'combined')
  if (!combined) return
  sections.value.push({
    uid: `${response.generation_id}-${Date.now()}`,
    generation_id: response.generation_id,
    filename: combined.filename,
    style: response.style,
    key: response.summary.key,
    bpm: response.summary.bpm,
    bars: response.summary.bars,
    repeat: 1,
  })
}

function remove(i: number) { sections.value.splice(i, 1) }

function moveUp(i: number) {
  if (i === 0) return
  ;[sections.value[i - 1], sections.value[i]] = [sections.value[i], sections.value[i - 1]]
}

function moveDown(i: number) {
  if (i >= sections.value.length - 1) return
  ;[sections.value[i + 1], sections.value[i]] = [sections.value[i], sections.value[i + 1]]
}

function setRepeat(i: number, n: number) {
  sections.value[i].repeat = Math.max(1, Math.min(8, n))
}

function formatStyle(id: string): string {
  return id.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

function buildEntries() {
  return sections.value.flatMap(s =>
    Array.from({ length: s.repeat }, () => ({ generation_id: s.generation_id, filename: s.filename }))
  )
}

async function togglePlayback() {
  if (isPlaying.value) {
    stopPlayer()
    return
  }
  building.value = true
  error.value = null
  try {
    const blob = await arrangeDownload(buildEntries())
    if (arrangeBlobUrl) URL.revokeObjectURL(arrangeBlobUrl)
    arrangeBlobUrl = URL.createObjectURL(blob)
    await toggle(arrangeBlobUrl, undefined, 'Arrangement')
  } catch (e) {
    error.value = errorMessage(e) ?? 'Playback failed'
  } finally {
    building.value = false
  }
}

async function downloadArrangement() {
  downloading.value = true
  error.value = null
  try {
    const blob = await arrangeDownload(buildEntries())
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'arrangement.mid'
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    error.value = errorMessage(e) ?? 'Export failed'
  } finally {
    downloading.value = false
  }
}

onUnmounted(() => {
  if (arrangeBlobUrl) URL.revokeObjectURL(arrangeBlobUrl)
})

defineExpose({ addGeneration })
</script>

<style scoped>
.arrange-panel {
  background: var(--panel);
  border: 1px solid var(--surface);
  border-radius: 10px;
  padding: 0.75rem 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.arrange-header {
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
}

.arrange-title {
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-dim);
  font-weight: 600;
}

.arrange-hint {
  font-size: 0.68rem;
  color: var(--text-faint);
}

/* Timeline */
.arrange-timeline {
  display: flex;
  height: 24px;
  border-radius: 5px;
  overflow: hidden;
  gap: 1px;
  background: var(--bg-deepest);
}

.timeline-block {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 0.35rem;
  background: var(--surface);
  overflow: hidden;
  min-width: 0;
  transition: background 0.15s;
  gap: 0.25rem;
}

.timeline-block.tl-playing {
  background: var(--accent-surface-strong);
  border-top: 2px solid var(--accent);
}

.tl-label {
  font-size: 0.58rem;
  color: var(--text-dim);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}

.tl-bars {
  font-size: 0.55rem;
  font-family: monospace;
  color: var(--text-faint);
  flex-shrink: 0;
}

/* Section list */
.arrange-sequence {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.arrange-section {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.35rem 0.6rem;
  background: var(--panel-deep);
  border: 1px solid var(--surface);
  border-radius: 6px;
  transition: border-color 0.15s;
}

.arrange-section.sec-playing {
  border-color: color-mix(in srgb, var(--accent) 27%, transparent);
}

.sec-order {
  font-size: 0.65rem;
  font-family: monospace;
  color: var(--text-faint);
  width: 14px;
  flex-shrink: 0;
  text-align: center;
}

.sec-style {
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--text);
  min-width: 80px;
}

.sec-meta {
  font-size: 0.68rem;
  color: var(--text-dim);
  flex: 1;
  font-family: monospace;
}

.sec-repeat {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  flex-shrink: 0;
}

.rep-btn {
  width: 18px;
  height: 18px;
  background: var(--surface);
  border: 1px solid var(--surface-hover);
  border-radius: 3px;
  color: var(--text-dim);
  font-size: 0.75rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  line-height: 1;
}
.rep-btn:hover:not(:disabled) { color: var(--accent); border-color: color-mix(in srgb, var(--accent) 33%, transparent); }
.rep-btn:disabled { opacity: 0.3; cursor: default; }

.rep-count {
  font-size: 0.68rem;
  font-family: monospace;
  color: var(--accent);
  width: 20px;
  text-align: center;
}

.sec-actions {
  display: flex;
  gap: 0.25rem;
  flex-shrink: 0;
}

.sec-btn {
  width: 22px;
  height: 22px;
  background: var(--surface);
  border: 1px solid var(--surface-hover);
  border-radius: 4px;
  color: var(--text-dim);
  font-size: 0.65rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  transition: background 0.15s, color 0.15s;
}
.sec-btn:hover:not(:disabled) { background: var(--surface-hover); color: var(--text); }
.sec-btn:disabled { opacity: 0.3; cursor: default; }
.sec-btn.remove:hover:not(:disabled) { color: var(--error); }

.arrange-empty {
  font-size: 0.72rem;
  color: var(--text-faint);
  text-align: center;
  padding: 0.5rem 0;
}

.arrange-footer {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.arrange-total {
  font-size: 0.72rem;
  color: var(--text-dim);
  flex: 1;
}

.arrange-play-btn {
  font-size: 0.75rem;
  padding: 0.3rem 0.75rem;
  background: var(--accent-surface);
  border: 1px solid color-mix(in srgb, var(--accent) 27%, transparent);
  border-radius: 5px;
  color: var(--accent);
  cursor: pointer;
  transition: background 0.15s;
}
.arrange-play-btn:hover:not(:disabled) { background: var(--accent-surface-strong); }
.arrange-play-btn.playing { background: var(--accent-surface-strong); border-color: var(--accent); }
.arrange-play-btn:disabled { opacity: 0.6; cursor: default; }

.arrange-dl-btn {
  font-size: 0.75rem;
  padding: 0.3rem 0.65rem;
  background: var(--panel-deep);
  border: 1px solid var(--surface);
  border-radius: 5px;
  color: var(--text-dim);
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.arrange-dl-btn:hover:not(:disabled) { background: var(--surface); color: var(--text); }
.arrange-dl-btn:disabled { opacity: 0.6; cursor: default; }

.arrange-error {
  font-size: 0.72rem;
  color: var(--error);
  padding: 0.25rem 0.5rem;
  background: var(--error-surface);
  border-radius: 4px;
}
</style>
