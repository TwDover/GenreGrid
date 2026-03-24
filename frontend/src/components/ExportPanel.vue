<template>
  <div v-if="history.length" class="export-panel">
    <div class="history-header">
      <span class="history-title">Generations</span>
      <span class="history-count">{{ history.length }}</span>
    </div>
    <div class="history-list">
      <div
        v-for="response in history"
        :key="response.generation_id"
        class="history-entry"
        :class="{ expanded: expandedId === response.generation_id }"
      >
        <button class="history-row" @click="toggle(response.generation_id)">
          <span class="entry-style">{{ formatStyle(response.style) }}</span>
          <span class="entry-meta">{{ response.summary.key }} · {{ response.summary.bpm }} BPM · {{ response.summary.bars }} bars</span>
          <span class="entry-id">{{ response.generation_id }}</span>
          <span class="entry-chevron">{{ expandedId === response.generation_id ? '▲' : '▼' }}</span>
        </button>
        <div v-if="expandedId === response.generation_id" class="entry-body">
          <div class="seed-row">
            <span class="seed-label">Seed</span>
            <span class="seed-value">{{ response.seed }}</span>
            <button class="seed-action" @click.stop="copy(response.seed)" :title="'Copy seed'">
              {{ copied === response.seed ? '✓' : 'Copy' }}
            </button>
            <button class="seed-action replay" @click.stop="$emit('replay', response)" title="Load these settings into the form">
              Replay
            </button>
          </div>
          <div class="part-cards">
            <PartCard v-for="file in response.files" :key="file.part" :file="file" />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import PartCard from './PartCard.vue'
import type { GenerateResponse } from '../types/midi'

const props = defineProps<{ history: GenerateResponse[] }>()
defineEmits<{ (e: 'replay', response: GenerateResponse): void }>()

const expandedId = ref<string | null>(null)
const copied = ref<number | null>(null)

watch(() => props.history[0], (newest) => {
  if (newest) expandedId.value = newest.generation_id
}, { immediate: true })

function toggle(id: string) {
  expandedId.value = expandedId.value === id ? null : id
}

function formatStyle(id: string): string {
  return id.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

function copy(seed: number) {
  navigator.clipboard.writeText(String(seed))
  copied.value = seed
  setTimeout(() => { copied.value = null }, 2000)
}
</script>

<style scoped>
.history-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}

.history-title {
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #8888a0;
}

.history-count {
  font-size: 0.7rem;
  background: #2a2a3e;
  color: #8888a0;
  border-radius: 10px;
  padding: 0.1rem 0.5rem;
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.history-entry {
  background: #1a1a24;
  border: 1px solid #2a2a3e;
  border-radius: 10px;
  overflow: hidden;
  transition: border-color 0.15s;
}

.history-entry.expanded {
  border-color: #a78bfa;
}

.history-row {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 1rem;
  background: none;
  border: none;
  color: #e0e0e8;
  cursor: pointer;
  text-align: left;
}

.history-row:hover { background: #22223a; }

.entry-style {
  font-weight: 600;
  font-size: 0.9rem;
  min-width: 100px;
}

.entry-meta {
  font-size: 0.8rem;
  color: #8888a0;
  flex: 1;
}

.entry-id {
  font-size: 0.72rem;
  font-family: monospace;
  color: #55556a;
}

.entry-chevron {
  font-size: 0.65rem;
  color: #55556a;
}

.entry-body {
  padding: 0 1rem 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.seed-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  background: #12121a;
  border-radius: 6px;
  border: 1px solid #2a2a3e;
}

.seed-label {
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #55556a;
}

.seed-value {
  font-family: monospace;
  font-size: 0.82rem;
  color: #a78bfa;
  flex: 1;
}

.seed-action {
  font-size: 0.75rem;
  padding: 0.2rem 0.6rem;
  background: #2a2a3e;
  border: 1px solid #3a3a54;
  border-radius: 4px;
  color: #8888a0;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.seed-action:hover { background: #3a3a54; color: #e0e0e8; }

.seed-action.replay {
  color: #a78bfa;
  border-color: #a78bfa44;
}

.seed-action.replay:hover { background: #3b1f6e; color: #c4b5fd; }

.part-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 0.75rem;
}
</style>
