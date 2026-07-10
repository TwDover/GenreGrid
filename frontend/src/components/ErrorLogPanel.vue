<!--
  GenreGrid — a style-based MIDI generator.
  Copyright (C) 2026 Tw Dover

  This program is free software: you can redistribute it and/or modify it under
  the terms of the GNU General Public License v3 or (at your option) any later
  version. Distributed WITHOUT ANY WARRANTY. See <https://www.gnu.org/licenses/>.
-->
<template>
  <div v-if="isOpen" class="elp-overlay" @click.self="close" @keydown.esc="close">
    <div class="elp-modal">
      <div class="elp-header">
        <span class="elp-title">Error Log <span class="elp-count">{{ entries.length }}</span></span>
        <div class="elp-actions">
          <button class="elp-btn" :disabled="!entries.length" @click="copyAll">{{ copied ? '✓ Copied' : 'Copy all' }}</button>
          <button class="elp-btn" :disabled="!entries.length" @click="clear">Clear</button>
          <button class="elp-close" @click="close" title="Close">✕</button>
        </div>
      </div>
      <p v-if="logFileHint" class="elp-hint">{{ logFileHint }}</p>
      <div v-if="!entries.length" class="elp-empty">Nothing logged this session — that's good.</div>
      <div v-else class="elp-list">
        <div v-for="e in entries" :key="e.id" class="elp-entry">
          <button class="elp-entry-head" @click="toggleExpand(e.id)">
            <span class="elp-time">{{ formatTime(e.timestamp) }}</span>
            <span class="elp-context">{{ e.context }}</span>
            <span class="elp-message">{{ e.message }}</span>
            <span class="elp-chevron">{{ expanded.has(e.id) ? '▲' : '▼' }}</span>
          </button>
          <pre v-if="expanded.has(e.id)" class="elp-stack">{{ e.stack || '(no stack trace available)' }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useErrorLog, type ErrorLogEntry } from '../composables/useErrorLog'

const { entries, isOpen, close, clear: clearLog } = useErrorLog()
const expanded = ref<Set<number>>(new Set())
const copied = ref(false)

const isElectron = typeof window !== 'undefined' && !!(window as any).electronAPI
const logFileHint = isElectron
  ? 'Also written to logs/renderer-errors.log next to backend.log, in case the app closes before you copy this.'
  : ''

function toggleExpand(id: number) {
  const next = new Set(expanded.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expanded.value = next
}

function formatTime(iso: string): string {
  try { return new Date(iso).toLocaleTimeString() } catch { return iso }
}

function formatEntry(e: ErrorLogEntry): string {
  return `[${e.timestamp}] ${e.context}: ${e.message}${e.stack ? `\n${e.stack}` : ''}`
}

async function copyAll() {
  const text = entries.value.map(formatEntry).join('\n\n')
  try {
    await navigator.clipboard.writeText(text)
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  } catch { /* clipboard unavailable — nothing to fall back to here */ }
}

function clear() {
  clearLog()
  expanded.value = new Set()
}
</script>

<style scoped>
.elp-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.65);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 300;
}

.elp-modal {
  background: var(--panel);
  border: 1px solid var(--surface);
  border-radius: 12px;
  padding: 1.25rem 1.5rem;
  width: 640px;
  max-width: 92vw;
  max-height: 78vh;
  display: flex;
  flex-direction: column;
}

.elp-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.5rem;
  flex-shrink: 0;
}

.elp-title {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text);
  letter-spacing: 0.02em;
  display: flex;
  align-items: center;
  gap: 0.4rem;
}

.elp-count {
  font-size: 0.65rem;
  font-family: monospace;
  color: var(--text-dim);
  background: var(--surface);
  border-radius: 10px;
  padding: 0.05rem 0.5rem;
}

.elp-actions { display: flex; align-items: center; gap: 0.4rem; }

.elp-btn {
  font-size: 0.72rem;
  padding: 0.3rem 0.65rem;
  border-radius: 6px;
  cursor: pointer;
  border: 1px solid var(--surface);
  background: var(--surface);
  color: var(--text-dim);
  transition: background 0.15s, color 0.15s;
}
.elp-btn:hover:not(:disabled) { background: var(--surface-hover); color: var(--text); }
.elp-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.elp-close {
  background: none;
  border: none;
  color: var(--text-dim);
  font-size: 0.9rem;
  cursor: pointer;
  padding: 0 0.2rem;
}
.elp-close:hover { color: var(--text); }

.elp-hint {
  font-size: 0.68rem;
  color: var(--text-faint);
  margin: 0 0 0.75rem;
  flex-shrink: 0;
}

.elp-empty {
  font-size: 0.78rem;
  color: var(--text-faint);
  text-align: center;
  padding: 2rem 0;
}

.elp-list {
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.elp-entry {
  background: var(--panel-deep);
  border: 1px solid var(--surface);
  border-radius: 6px;
  overflow: hidden;
}

.elp-entry-head {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.45rem 0.6rem;
  background: none;
  border: none;
  cursor: pointer;
  text-align: left;
  font-family: inherit;
}
.elp-entry-head:hover { background: var(--surface); }

.elp-time {
  font-size: 0.65rem;
  font-family: monospace;
  color: var(--text-faint);
  flex-shrink: 0;
}

.elp-context {
  font-size: 0.68rem;
  font-weight: 600;
  color: var(--accent);
  flex-shrink: 0;
  white-space: nowrap;
}

.elp-message {
  font-size: 0.72rem;
  color: var(--text-soft);
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.elp-chevron {
  font-size: 0.6rem;
  color: var(--text-faint);
  flex-shrink: 0;
}

.elp-stack {
  margin: 0;
  padding: 0.6rem 0.75rem;
  background: var(--bg-deepest);
  border-top: 1px solid var(--surface);
  font-size: 0.68rem;
  color: var(--text-dim);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 240px;
  overflow-y: auto;
}
</style>
