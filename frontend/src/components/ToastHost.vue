<!--
  GenreGrid — a style-based MIDI generator.
  Copyright (C) 2026 Tw Dover

  This program is free software: you can redistribute it and/or modify it under
  the terms of the GNU General Public License v3 or (at your option) any later
  version. Distributed WITHOUT ANY WARRANTY. See <https://www.gnu.org/licenses/>.
-->
<template>
  <div class="toast-host" aria-live="polite">
    <TransitionGroup name="toast">
      <div
        v-for="t in toasts"
        :key="t.id"
        class="toast"
        :class="t.kind"
        role="status"
        @click="dismiss(t.id)"
      >
        <span class="toast-icon">{{ t.kind === 'error' ? '✕' : '✓' }}</span>
        <span class="toast-msg">{{ t.message }}</span>
      </div>
    </TransitionGroup>
  </div>
</template>

<script setup lang="ts">
import { useToasts } from '../composables/useToasts'

const { toasts, dismiss } = useToasts()
</script>

<style scoped>
.toast-host {
  position: fixed;
  right: 1rem;
  bottom: 1rem;
  z-index: 300;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  pointer-events: none;
}

.toast {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  max-width: 320px;
  background: var(--panel);
  border: 1px solid var(--surface);
  border-left: 3px solid var(--accent);
  border-radius: 6px;
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.5);
  cursor: pointer;
  pointer-events: auto;
}
.toast.error { border-left-color: var(--error); }

.toast-icon {
  font-size: 0.7rem;
  color: var(--accent);
  flex-shrink: 0;
}
.toast.error .toast-icon { color: var(--error); }

.toast-msg {
  font-size: 0.75rem;
  color: var(--text-soft);
  line-height: 1.3;
}

.toast-enter-active,
.toast-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}
.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateX(16px);
}
</style>
