<template>
  <div class="library-panel">
    <div class="lib-toolbar">
      <select v-model="filterStyle" class="style-filter" @change="load">
        <option value="" disabled>Select a style…</option>
        <option v-for="s in styles" :key="s.id" :value="s.id">{{ formatStyle(s.id) }}</option>
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
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { fetchLibrary } from '../services/api'
import type { LibraryEntry, StyleInfo } from '../types/midi'

const props = defineProps<{ styles: StyleInfo[] }>()
defineEmits<{ (e: 'replay', entry: LibraryEntry): void }>()

const entries = ref<LibraryEntry[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const filterStyle = ref('')

const dims = ['harmonic', 'rhythm', 'register', 'density', 'mix'] as const

async function load() {
  if (!filterStyle.value) return
  loading.value = true
  error.value = null
  try {
    entries.value = await fetchLibrary(filterStyle.value)
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

function pct(v: number): number {
  return Math.round(v * 100)
}

function dimColor(v: number): string {
  if (v >= 0.82) return '#34d399'
  if (v >= 0.68) return '#60a5fa'
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
  background: #1a1a24;
  border: 1px solid #2a2a3e;
  border-radius: 6px;
  color: #e0e0e8;
  font-size: 0.8rem;
  padding: 0.3rem 0.5rem;
  cursor: pointer;
  flex: 1;
}

.style-filter:focus { outline: none; border-color: #a78bfa; }

.lib-count {
  font-size: 0.72rem;
  color: #55556a;
  white-space: nowrap;
}

.lib-empty {
  font-size: 0.82rem;
  color: #55556a;
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
  background: #1a1a24;
  border: 1px solid #2a2a3e;
  border-radius: 8px;
  padding: 0.65rem 0.85rem;
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
}

.lib-entry-main {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  flex-wrap: wrap;
}

.lib-style {
  font-weight: 600;
  font-size: 0.85rem;
  color: #e0e0e8;
}

.lib-meta {
  font-size: 0.78rem;
  color: #8888a0;
  flex: 1;
}

.lib-date {
  font-size: 0.72rem;
  color: #55556a;
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
  color: #a78bfa;
  margin-left: 0.3rem;
}

.lib-replay {
  font-size: 0.75rem;
  padding: 0.2rem 0.65rem;
  background: #2a2a3e;
  border: 1px solid #a78bfa44;
  border-radius: 4px;
  color: #a78bfa;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.lib-replay:hover { background: #3b1f6e; color: #c4b5fd; }
</style>
