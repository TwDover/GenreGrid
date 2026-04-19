<template>
  <div class="library-panel">
    <div class="lib-toolbar">
      <select v-model="filterStyle" class="style-filter" @change="load">
        <option value="" disabled>Select a style…</option>
        <option v-for="s in styles" :key="s.id" :value="s.id">{{ formatStyle(s.id) }}{{ counts[s.id] ? ` (${counts[s.id]})` : '' }}</option>
      </select>
      <span class="lib-count" v-if="filterStyle && !loading">{{ entries.length }} saved</span>
    </div>

    <div v-if="loading" class="lib-empty">Loading…</div>
    <div v-else-if="error" class="lib-empty lib-error">{{ error }}</div>
    <div v-else-if="!filterStyle" class="lib-empty">Select a style to browse saved generations.</div>
    <div v-else-if="entries.length === 0" class="lib-empty">No saved generations for this style yet.</div>

    <div v-else class="lib-list">
      <div v-for="entry in entries" :key="entry.gen_id" class="lib-entry">
        <div class="lib-entry-main">
          <button
            class="lib-play"
            :class="{ playing: isPlayingEntry(entry.gen_id) }"
            :disabled="isLoading && !isPlayingEntry(entry.gen_id)"
            @click="toggleEntry(entry)"
            :title="isPlayingEntry(entry.gen_id) ? 'Stop' : 'Preview'"
          >
            <span v-if="isLoading && !isPlayingEntry(entry.gen_id)">…</span>
            <span v-else>{{ isPlayingEntry(entry.gen_id) ? '■' : '▶' }}</span>
          </button>
          <span class="lib-style">{{ formatStyle(entry.style_id) }}</span>
          <span class="lib-meta">{{ entry.key }} {{ entry.scale }} · {{ entry.bpm }} BPM · {{ entry.bars }} bars</span>
          <span class="lib-date">{{ formatDate(entry.saved_at) }}</span>
        </div>
        <div class="lib-entry-footer">
          <div class="lib-quality">
            <span
              v-for="dim in dims"
              :key="dim"
              class="lib-dim"
              :style="{ background: dimColor(entry.quality[dim]) }"
              :title="`${dim}: ${pct(entry.quality[dim])}%`"
            ></span>
            <span class="lib-total">{{ pct(entry.quality.total) }}%</span>
          </div>
          <button class="lib-replay" @click="$emit('replay', entry)">Replay</button>
        </div>
        <div class="lib-roll" v-if="getMidiData(entryUrl(entry.gen_id))">
          <PianoRoll
            :notes="getMidiData(entryUrl(entry.gen_id))!.notes"
            :duration="getMidiData(entryUrl(entry.gen_id))!.duration"
            :playing="isPlayingEntry(entry.gen_id)"
            :keyRoot="entry.key.split(' ')[0]"
            :scale="entry.scale"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { fetchLibrary, fetchLibraryCounts } from '../services/api'
import { useMidiPlayer } from '../composables/useMidiPlayer'
import PianoRoll from './PianoRoll.vue'
import type { LibraryEntry, StyleInfo } from '../types/midi'

defineProps<{ styles: StyleInfo[] }>()
defineEmits<{ (e: 'replay', entry: LibraryEntry): void }>()

const entries = ref<LibraryEntry[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const filterStyle = ref('')
const counts = ref<Record<string, number>>({})

const { toggle, currentlyPlaying, isLoading, getMidiData, prefetchMidi } = useMidiPlayer()

onMounted(async () => { counts.value = await fetchLibraryCounts() })

const dims = ['harmonic', 'rhythm', 'register', 'density', 'mix'] as const

function entryUrl(gen_id: string): string {
  return `/exports/${gen_id}/combined.mid`
}

function isPlayingEntry(gen_id: string): boolean {
  return currentlyPlaying.value === entryUrl(gen_id)
}

async function toggleEntry(entry: LibraryEntry) {
  await toggle(entryUrl(entry.gen_id), entry.style_id, formatStyle(entry.style_id))
}

async function load() {
  if (!filterStyle.value) return
  loading.value = true
  error.value = null
  try {
    entries.value = await fetchLibrary(filterStyle.value)
    // Prefetch MIDI for piano rolls
    for (const e of entries.value) prefetchMidi(entryUrl(e.gen_id))
  } catch {
    error.value = 'Could not load library'
  } finally {
    loading.value = false
  }
}

function formatStyle(id: string): string {
  return id.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function pct(v: number): number { return Math.round(v * 100) }

function dimColor(v: number): string {
  if (v >= 0.82) return '#34d399'
  if (v >= 0.68) return '#00c8ff'
  if (v >= 0.52) return '#fbbf24'
  return '#f87171'
}
</script>

<style scoped>
.library-panel {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.lib-toolbar {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.style-filter {
  background: #060f14;
  border: 1px solid #0d2535;
  border-radius: 6px;
  color: #e0e0e8;
  font-size: 0.8rem;
  padding: 0.3rem 0.5rem;
  cursor: pointer;
  flex: 1;
}
.style-filter:focus { outline: none; border-color: #00c8ff; }

.lib-count {
  font-size: 0.72rem;
  color: #2a4550;
  white-space: nowrap;
}

.lib-empty {
  font-size: 0.82rem;
  color: #2a4550;
  text-align: center;
  padding: 2rem 1rem;
}
.lib-error { color: #f87171; }

.lib-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.lib-entry {
  background: #060f14;
  border: 1px solid #0d2535;
  border-radius: 8px;
  padding: 0.65rem 0.85rem;
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  transition: border-color 0.15s;
}

.lib-entry:has(.lib-play.playing) {
  border-color: #00c8ff44;
}

.lib-entry-main {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  flex-wrap: wrap;
}

.lib-play {
  width: 26px;
  height: 26px;
  flex-shrink: 0;
  background: #0d2535;
  border: 1px solid #122f40;
  border-radius: 5px;
  color: #00c8ff;
  font-size: 0.75rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  transition: background 0.15s;
}
.lib-play:hover:not(:disabled) { background: #122f40; }
.lib-play.playing { background: #003450; border-color: #00c8ff; }
.lib-play:disabled { opacity: 0.5; cursor: not-allowed; }

.lib-style {
  font-weight: 600;
  font-size: 0.85rem;
  color: #e0e0e8;
}

.lib-meta {
  font-size: 0.78rem;
  color: #4a7080;
  flex: 1;
}

.lib-date {
  font-size: 0.72rem;
  color: #2a4550;
}

.lib-entry-footer {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.lib-quality {
  display: flex;
  align-items: center;
  gap: 3px;
  flex: 1;
}

.lib-dim {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.lib-total {
  font-size: 0.72rem;
  font-family: monospace;
  color: #00c8ff;
  margin-left: 0.3rem;
}

.lib-replay {
  font-size: 0.75rem;
  padding: 0.2rem 0.65rem;
  background: #0d2535;
  border: 1px solid #00c8ff44;
  border-radius: 4px;
  color: #00c8ff;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.lib-replay:hover { background: #003450; color: #7ae8ff; }

.lib-roll {
  margin-top: -0.1rem;
}
</style>
