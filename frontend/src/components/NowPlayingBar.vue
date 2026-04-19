<template>
  <div v-if="isLoading || currentlyPlaying" class="now-playing-bar">
    <span class="np-icon">{{ isLoading ? '⟳' : '▶' }}</span>
    <span v-if="isRecording" class="np-rec">● REC</span>
    <span v-else class="np-label">{{ nowPlayingLabel ?? '…' }}</span>
    <button
      class="np-loop"
      :class="{ active: looping }"
      @click="setLooping(!looping)"
      :disabled="isRecording"
      title="Toggle loop"
    >{{ looping ? '↻' : '↺' }}</button>
    <button class="np-stop" :disabled="isRecording" @click="stop" title="Stop playback (Space)">■</button>
  </div>
</template>

<script setup lang="ts">
import { useMidiPlayer } from '../composables/useMidiPlayer'

const { currentlyPlaying, nowPlayingLabel, isLoading, stop, looping, setLooping, isRecording } = useMidiPlayer()
</script>

<style scoped>
.now-playing-bar {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.25rem 0.75rem;
  background: #001e35;
  border: 1px solid #00c8ff44;
  border-radius: 6px;
  min-width: 0;
  max-width: 220px;
}

.np-icon {
  font-size: 0.7rem;
  color: #00c8ff;
  flex-shrink: 0;
  animation: v-bind("isLoading ? 'spin 1s linear infinite' : 'none'");
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.np-label {
  font-size: 0.72rem;
  color: #7ae8ff;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
  min-width: 0;
  font-family: monospace;
  text-transform: capitalize;
}

.np-rec {
  font-size: 0.72rem;
  color: #f87171;
  font-family: monospace;
  flex: 1;
  animation: blink 1s step-start infinite;
}

@keyframes blink {
  50% { opacity: 0.4; }
}

.np-loop {
  background: none;
  border: none;
  color: #4a7080;
  cursor: pointer;
  font-size: 0.85rem;
  padding: 0;
  flex-shrink: 0;
  line-height: 1;
  transition: color 0.15s;
}
.np-loop:hover:not(:disabled) { color: #00c8ff; }
.np-loop.active { color: #00c8ff; }
.np-loop:disabled { opacity: 0.5; cursor: not-allowed; }

.np-stop {
  background: none;
  border: none;
  color: #4a7080;
  cursor: pointer;
  font-size: 0.65rem;
  padding: 0;
  flex-shrink: 0;
  line-height: 1;
  transition: color 0.15s;
}
.np-stop:hover:not(:disabled) { color: #f87171; }
.np-stop:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
