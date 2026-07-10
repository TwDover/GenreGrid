<!--
  GenreGrid — a style-based MIDI generator.
  Copyright (C) 2026 Tw Dover

  This program is free software: you can redistribute it and/or modify it under
  the terms of the GNU General Public License v3 or (at your option) any later
  version. Distributed WITHOUT ANY WARRANTY. See <https://www.gnu.org/licenses/>.
-->
<template>
  <div v-if="promptState.active" class="dnp-overlay" @click.self="cancel" @keydown.esc="cancel">
    <div class="dnp-modal">
      <div class="dnp-title">{{ promptState.title }}</div>
      <div class="dnp-field">
        <input
          ref="inputRef"
          v-model="name"
          type="text"
          class="dnp-input"
          @keydown.enter="submit"
          @keydown.esc="cancel"
        />
        <span class="dnp-ext">.{{ promptState.extension }}</span>
      </div>
      <div class="dnp-actions">
        <button class="dnp-btn dnp-cancel" @click="cancel">Cancel</button>
        <button class="dnp-btn dnp-save" @click="submit">Save</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { useDownloadPrompt } from '../composables/useDownloadPrompt'

const { promptState, confirm, cancel } = useDownloadPrompt()
const name = ref('')
const inputRef = ref<HTMLInputElement | null>(null)

watch(() => promptState.value.active, async (active) => {
  if (!active) return
  name.value = promptState.value.defaultName
  await nextTick()
  inputRef.value?.focus()
  inputRef.value?.select()
})

function submit() {
  confirm(name.value)
}
</script>

<style scoped>
.dnp-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.65);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 300;
}

.dnp-modal {
  background: var(--panel);
  border: 1px solid var(--surface);
  border-radius: 12px;
  padding: 1.25rem 1.5rem;
  min-width: 320px;
}

.dnp-title {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text);
  letter-spacing: 0.02em;
  margin-bottom: 0.85rem;
}

.dnp-field {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin-bottom: 1rem;
}

.dnp-input {
  flex: 1;
  min-width: 0;
}

.dnp-ext {
  font-family: monospace;
  font-size: 0.85rem;
  color: var(--text-dim);
  flex-shrink: 0;
}

.dnp-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
}

.dnp-btn {
  font-size: 0.78rem;
  padding: 0.4rem 0.9rem;
  border-radius: 6px;
  cursor: pointer;
  border: 1px solid var(--surface);
  background: var(--surface);
  color: var(--text-dim);
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}
.dnp-btn:hover { background: var(--surface-hover); }

.dnp-save {
  border-color: color-mix(in srgb, var(--accent) 40%, transparent);
  background: var(--accent-surface);
  color: var(--accent);
}
.dnp-save:hover { background: var(--accent-surface-strong); }
</style>
