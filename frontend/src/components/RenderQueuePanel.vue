<!--
  GenreGrid — a style-based MIDI generator.
  Copyright (C) 2026 Tw Dover

  This program is free software: you can redistribute it and/or modify it under
  the terms of the GNU General Public License v3 or (at your option) any later
  version. Distributed WITHOUT ANY WARRANTY. See <https://www.gnu.org/licenses/>.
-->
<template>
  <div v-if="isOpen" class="rqp-overlay" @click.self="close" @keydown.esc="close">
    <div class="rqp-modal">
      <div class="rqp-header">
        <span class="rqp-title">Downloads <span class="rqp-count">{{ jobs.length }}</span></span>
        <div class="rqp-actions">
          <button class="rqp-btn" :disabled="!hasFinished" @click="clearFinished">Clear finished</button>
          <button class="rqp-close" @click="close" title="Close">✕</button>
        </div>
      </div>
      <p class="rqp-hint">WAV renders and ZIP downloads keep running even if you switch tabs — this panel is where you can check on them and save again if you missed one.</p>
      <div v-if="!jobs.length" class="rqp-empty">Nothing downloaded yet.</div>
      <div v-else class="rqp-list">
        <div v-for="j in jobs" :key="j.id" class="rqp-job" :class="j.status">
          <div class="rqp-job-row">
            <span class="rqp-job-label">{{ j.label }}</span>
            <span class="rqp-job-status">
              <span v-if="j.status === 'rendering'">{{ Math.round(j.progress * 100) }}%</span>
              <span v-else-if="j.status === 'done'" class="rqp-done">✓ done</span>
              <span v-else class="rqp-error-tag">✕ failed</span>
            </span>
            <button v-if="j.status === 'done'" class="rqp-mini-btn" @click="redownload(j.id)" title="Download again">↓ again</button>
            <button v-if="j.status !== 'rendering'" class="rqp-mini-btn" @click="removeJob(j.id)" title="Remove from list">✕</button>
          </div>
          <div v-if="j.status === 'rendering'" class="rqp-bar-track">
            <div class="rqp-bar-fill" :style="{ width: `${Math.round(j.progress * 100)}%` }" />
          </div>
          <div v-if="j.status === 'error'" class="rqp-error-msg">{{ j.error }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRenderQueue } from '../composables/useRenderQueue'

const { jobs, isOpen, close, redownload, removeJob, clearFinished } = useRenderQueue()
const hasFinished = computed(() => jobs.value.some(j => j.status !== 'rendering'))
</script>

<style scoped>
.rqp-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.65);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 300;
}

.rqp-modal {
  background: var(--panel);
  border: 1px solid var(--surface);
  border-radius: 12px;
  padding: 1.25rem 1.5rem;
  width: 520px;
  max-width: 92vw;
  max-height: 78vh;
  display: flex;
  flex-direction: column;
}

.rqp-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.5rem;
  flex-shrink: 0;
}

.rqp-title {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text);
  letter-spacing: 0.02em;
  display: flex;
  align-items: center;
  gap: 0.4rem;
}

.rqp-count {
  font-size: 0.65rem;
  font-family: monospace;
  color: var(--text-dim);
  background: var(--surface);
  border-radius: 10px;
  padding: 0.05rem 0.5rem;
}

.rqp-actions { display: flex; align-items: center; gap: 0.4rem; }

.rqp-btn {
  font-size: 0.72rem;
  padding: 0.3rem 0.65rem;
  border-radius: 6px;
  cursor: pointer;
  border: 1px solid var(--surface);
  background: var(--surface);
  color: var(--text-dim);
  transition: background 0.15s, color 0.15s;
}
.rqp-btn:hover:not(:disabled) { background: var(--surface-hover); color: var(--text); }
.rqp-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.rqp-close {
  background: none;
  border: none;
  color: var(--text-dim);
  font-size: 0.9rem;
  cursor: pointer;
  padding: 0 0.2rem;
}
.rqp-close:hover { color: var(--text); }

.rqp-hint {
  font-size: 0.68rem;
  color: var(--text-faint);
  margin: 0 0 0.75rem;
  flex-shrink: 0;
}

.rqp-empty {
  font-size: 0.78rem;
  color: var(--text-faint);
  text-align: center;
  padding: 2rem 0;
}

.rqp-list {
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.rqp-job {
  background: var(--panel-deep);
  border: 1px solid var(--surface);
  border-radius: 6px;
  padding: 0.5rem 0.65rem;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}
.rqp-job.error { border-color: color-mix(in srgb, var(--error) 33%, transparent); }
.rqp-job.done { border-color: color-mix(in srgb, var(--success) 27%, transparent); }

.rqp-job-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.rqp-job-label {
  font-size: 0.75rem;
  color: var(--text);
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rqp-job-status {
  font-size: 0.7rem;
  font-family: monospace;
  color: var(--accent);
  flex-shrink: 0;
}
.rqp-done { color: var(--success); }
.rqp-error-tag { color: var(--error); }

.rqp-mini-btn {
  font-size: 0.65rem;
  padding: 0.15rem 0.4rem;
  background: var(--surface);
  border: 1px solid var(--surface-hover);
  border-radius: 4px;
  color: var(--text-dim);
  cursor: pointer;
  flex-shrink: 0;
  transition: background 0.15s, color 0.15s;
}
.rqp-mini-btn:hover { background: var(--surface-hover); color: var(--text); }

.rqp-bar-track {
  height: 4px;
  border-radius: 2px;
  background: var(--surface);
  overflow: hidden;
}
.rqp-bar-fill {
  height: 100%;
  background: var(--accent);
  transition: width 0.2s;
}

.rqp-error-msg {
  font-size: 0.68rem;
  color: var(--error);
}
</style>
