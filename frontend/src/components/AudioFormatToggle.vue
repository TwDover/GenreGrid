<!--
  GenreGrid — a style-based MIDI generator.
  Copyright (C) 2026 Tw Dover

  This program is free software: you can redistribute it and/or modify it under
  the terms of the GNU General Public License as published by the Free Software
  Foundation, either version 3 of the License, or (at your option) any later
  version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
  <https://www.gnu.org/licenses/> for details.
-->
<!-- Segmented WAV / MP3 / OGG picker bound to the shared export-format state. -->
<template>
  <div class="fmt-toggle" role="radiogroup" aria-label="Audio export format">
    <button
      v-for="fmt in AUDIO_FORMATS"
      :key="fmt"
      class="fmt-btn"
      :class="{ active: audioFormat === fmt }"
      role="radio"
      :aria-checked="audioFormat === fmt"
      @click.stop="audioFormat = fmt"
      :title="fmt === 'wav' ? 'WAV — lossless, large' : fmt === 'mp3' ? 'MP3 — compressed (~190 kbps VBR), small & universal' : 'OGG Vorbis — compressed (~160 kbps)'"
    >{{ fmt.toUpperCase() }}</button>
  </div>
</template>

<script setup lang="ts">
import { AUDIO_FORMATS } from '../utils/audioEncoder'
import { useExportFormat } from '../composables/useExportFormat'

const { audioFormat } = useExportFormat()
</script>

<style scoped>
/* A single pill; the active segment washed with the accent. */
.fmt-toggle {
  display: inline-flex;
  border: 1px solid var(--surface);
  border-radius: var(--r-sm);
  overflow: hidden;
}
.fmt-btn {
  padding: 0.2rem 0.5rem;
  font-family: var(--f-mono);
  font-size: 0.66rem;
  letter-spacing: 0.04em;
  color: var(--text-faint);
  background: transparent;
  border: none;
  border-left: 1px solid var(--surface);
  cursor: pointer;
}
.fmt-btn:first-child { border-left: none; }
.fmt-btn:hover:not(.active) { color: var(--text); background: var(--panel); }
.fmt-btn.active { color: var(--accent); background: var(--accent-wash); font-weight: 600; }
</style>
