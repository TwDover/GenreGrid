<template>
  <div class="arrange-panel">
    <div class="arrange-header">
      <span class="arrange-title">Arrangement</span>
      <span class="arrange-hint">Add sections from your generations below</span>
    </div>

    <div class="arrange-sequence" v-if="sections.length">
      <div
        v-for="(sec, i) in sections"
        :key="sec.uid"
        class="arrange-section"
      >
        <span class="sec-order">{{ i + 1 }}</span>
        <span class="sec-style">{{ formatStyle(sec.style) }}</span>
        <span class="sec-meta">{{ sec.key }} · {{ sec.bpm }}bpm · {{ sec.bars }}bars</span>
        <div class="sec-actions">
          <button class="sec-btn" :disabled="i === 0" @click="moveUp(i)" title="Move up">↑</button>
          <button class="sec-btn" :disabled="i === sections.length - 1" @click="moveDown(i)" title="Move down">↓</button>
          <button class="sec-btn remove" @click="remove(i)" title="Remove">✕</button>
        </div>
      </div>
    </div>
    <div v-else class="arrange-empty">No sections yet — add them from your generations</div>

    <div class="arrange-footer" v-if="sections.length">
      <span class="arrange-total">{{ sections.length }} section{{ sections.length !== 1 ? 's' : '' }}</span>
      <button class="arrange-dl-btn" :disabled="downloading" @click="downloadArrangement">
        {{ downloading ? 'Building…' : '↓ Download Arrangement MIDI' }}
      </button>
    </div>
    <div v-if="error" class="arrange-error">{{ error }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { GenerateResponse } from '../types/midi'
import { arrangeDownload } from '../services/api'

interface ArrangeSection {
  uid: string
  generation_id: string
  filename: string
  style: string
  key: string
  bpm: number
  bars: number
}

const sections = ref<ArrangeSection[]>([])
const downloading = ref(false)
const error = ref<string | null>(null)

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
  })
}

function remove(i: number) {
  sections.value.splice(i, 1)
}

function moveUp(i: number) {
  if (i === 0) return
  ;[sections.value[i - 1], sections.value[i]] = [sections.value[i], sections.value[i - 1]]
}

function moveDown(i: number) {
  if (i >= sections.value.length - 1) return
  ;[sections.value[i + 1], sections.value[i]] = [sections.value[i], sections.value[i + 1]]
}

function formatStyle(id: string): string {
  return id.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

async function downloadArrangement() {
  downloading.value = true
  error.value = null
  try {
    const entries = sections.value.map(s => ({ generation_id: s.generation_id, filename: s.filename }))
    const blob = await arrangeDownload(entries)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'arrangement.mid'
    a.click()
    URL.revokeObjectURL(url)
  } catch (e: any) {
    error.value = e.message ?? 'Export failed'
  } finally {
    downloading.value = false
  }
}

defineExpose({ addGeneration })
</script>

<style scoped>
.arrange-panel {
  background: #060f14;
  border: 1px solid #0d2535;
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
  color: #4a7080;
  font-weight: 600;
}

.arrange-hint {
  font-size: 0.68rem;
  color: #2a4550;
}

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
  background: #040a0e;
  border: 1px solid #0d2535;
  border-radius: 6px;
}

.sec-order {
  font-size: 0.65rem;
  font-family: monospace;
  color: #2a4550;
  width: 14px;
  flex-shrink: 0;
  text-align: center;
}

.sec-style {
  font-size: 0.78rem;
  font-weight: 600;
  color: #e0e0e8;
  min-width: 90px;
}

.sec-meta {
  font-size: 0.68rem;
  color: #4a7080;
  flex: 1;
  font-family: monospace;
}

.sec-actions {
  display: flex;
  gap: 0.25rem;
  flex-shrink: 0;
}

.sec-btn {
  width: 22px;
  height: 22px;
  background: #0d2535;
  border: 1px solid #122f40;
  border-radius: 4px;
  color: #4a7080;
  font-size: 0.65rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  transition: background 0.15s, color 0.15s;
}
.sec-btn:hover:not(:disabled) { background: #122f40; color: #e0e0e8; }
.sec-btn:disabled { opacity: 0.3; cursor: default; }
.sec-btn.remove:hover:not(:disabled) { color: #f87171; }

.arrange-empty {
  font-size: 0.72rem;
  color: #2a4550;
  text-align: center;
  padding: 0.5rem 0;
}

.arrange-footer {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.arrange-total {
  font-size: 0.72rem;
  color: #4a7080;
}

.arrange-dl-btn {
  font-size: 0.75rem;
  padding: 0.3rem 0.75rem;
  background: #001e35;
  border: 1px solid #00c8ff44;
  border-radius: 5px;
  color: #00c8ff;
  cursor: pointer;
  transition: background 0.15s;
}
.arrange-dl-btn:hover:not(:disabled) { background: #003450; }
.arrange-dl-btn:disabled { opacity: 0.6; cursor: default; }

.arrange-error {
  font-size: 0.72rem;
  color: #f87171;
  padding: 0.25rem 0.5rem;
  background: #2a1010;
  border-radius: 4px;
}
</style>
