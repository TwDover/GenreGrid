<!--
  GenreGrid — a style-based MIDI generator.
  Copyright (C) 2026 Tw Dover

  This program is free software: you can redistribute it and/or modify it under
  the terms of the GNU General Public License v3 or (at your option) any later
  version. Distributed WITHOUT ANY WARRANTY. See <https://www.gnu.org/licenses/>.
-->
<template>
  <!-- Always mounted. An idle transport is still the answer to "where do I
       press play" — hiding it was what made playback feel like it lived in a
       different place every time. -->
  <div class="transport-bar" :class="{ idle: isIdle }">
    <!-- Transport controls -->
    <div class="tb-controls">
      <button
        class="tb-btn tb-play"
        :disabled="isLoading || isRecording || (isIdle && !cuedLabel)"
        @click="onPlayPause"
        :title="playTitle"
      >{{ isLoading ? '⟳' : (isIdle || isPaused) ? '▶' : '⏸' }}</button>
      <button class="tb-btn" :disabled="isRecording || isIdle" @click="stop" title="Stop playback (Space)">■</button>
      <button
        class="tb-btn"
        :class="{ active: looping }"
        :disabled="isRecording"
        @click="setLooping(!looping)"
        title="Toggle loop"
      >{{ looping ? '↻' : '↺' }}</button>
    </div>

    <!-- Track label -->
    <span v-if="isRecording" class="tb-rec">● REC</span>
    <span v-else class="tb-label" :class="{ 'tb-label-cued': isIdle }" :title="trackLabel">{{ trackLabel }}</span>

    <!-- Seek bar -->
    <div class="tb-seek">
      <span class="tb-time">{{ fmt(positionSeconds) }}</span>
      <input
        type="range"
        class="tb-seek-slider"
        min="0"
        :max="durationSeconds || 0"
        step="0.1"
        :value="positionSeconds"
        :disabled="isLoading || isRecording || !durationSeconds"
        @input="onSeek"
        title="Seek"
      />
      <span class="tb-time">{{ fmt(durationSeconds) }}</span>
    </div>

    <!-- Per-part mute / solo -->
    <div v-if="!isRecording" class="tb-parts">
      <button
        v-for="ch in PLAYER_PARTS"
        :key="ch"
        class="tb-mute"
        :class="{ muted: channelMuted[ch] }"
        @click="(e: MouseEvent) => e.shiftKey ? soloPart(ch) : toggleMute(ch)"
        :title="`${channelMuted[ch] ? 'Unmute' : 'Mute'} ${ch.replace('_', ' ')} — shift-click to solo`"
      >{{ chipLabel(ch) }}</button>
    </div>

    <!-- Volume -->
    <div class="tb-volume">
      <span class="tb-vol-icon">{{ volume === 0 ? '🔇' : volume < 40 ? '🔈' : '🔊' }}</span>
      <input
        type="range"
        min="0"
        max="100"
        :value="volume"
        @input="setVolume(+($event.target as HTMLInputElement).value)"
        class="tb-vol-slider"
        title="Master volume"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useMidiPlayer, PLAYER_PARTS, type PlayerPart } from '../composables/useMidiPlayer'

const {
  currentlyPlaying, nowPlayingLabel, isLoading, isRecording,
  stop, looping, setLooping, channelMuted, toggleMute, soloPart,
  positionSeconds, durationSeconds, seek, isPaused, togglePause,
  volume, setVolume, playCued, cuedLabel,
} = useMidiPlayer()

const isIdle = computed(() => !currentlyPlaying.value && !isLoading.value)

// Idle shows the cued track (what ▶ would start) so the bar is never a blank
// row of dead controls.
const trackLabel = computed(() => {
  if (isLoading.value) return 'Loading…'
  if (!isIdle.value) return nowPlayingLabel.value ?? '…'
  return cuedLabel.value ?? 'Nothing loaded'
})

const playTitle = computed(() => {
  if (isIdle.value) return cuedLabel.value ? `Play ${cuedLabel.value}` : 'Generate something to play'
  return isPaused.value ? 'Resume' : 'Pause'
})

function onPlayPause() {
  if (isIdle.value) playCued()
  else togglePause()
}

const chipLabel = (ch: PlayerPart) => (
  { drums: 'D', bass: 'B', chords: 'Ch', melody: 'M', arpeggio: 'A', pads: 'P', counter_melody: 'Cm' }[ch]
)

function fmt(s: number): string {
  const t = Math.max(0, Math.floor(s))
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, '0')}`
}

function onSeek(e: Event) {
  seek(+(e.target as HTMLInputElement).value)
}
</script>

<style scoped>
/* Docked to the bottom of the shell. Fixed height in both states so nothing
 * above it ever reflows when playback starts or stops. */
.transport-bar {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem 1rem;
  height: 52px;
  background: var(--accent-surface);
  border-top: 1px solid color-mix(in srgb, var(--accent) 25%, transparent);
  min-width: 0;
  flex-shrink: 0;
}
.transport-bar.idle { background: var(--panel); border-top-color: var(--surface); }

.tb-controls { display: flex; gap: 0.35rem; flex-shrink: 0; }

.tb-btn {
  width: 32px;
  height: 32px;
  background: var(--surface);
  border: 1px solid var(--surface-hover);
  border-radius: 6px;
  color: var(--accent);
  font-size: 0.8rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
  transition: background 0.15s, border-color 0.15s;
}
.tb-btn:hover:not(:disabled) { background: var(--surface-hover); }
.tb-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.tb-btn.active { border-color: var(--accent); background: var(--accent-surface-strong); }

/* The one true play button — solid accent, wider than its neighbours. */
.tb-play {
  width: 44px;
  background: var(--accent);
  border-color: var(--accent);
  color: var(--on-accent);
  font-size: 0.9rem;
}
.tb-play:hover:not(:disabled) { background: var(--accent); filter: brightness(1.12); }

.tb-label {
  font-size: 0.75rem;
  font-family: monospace;
  color: var(--accent-bright);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 220px;
  min-width: 90px;
  flex-shrink: 1;
  text-transform: capitalize;
}
.tb-label-cued { color: var(--text-dim); }

.tb-rec {
  font-size: 0.75rem;
  color: var(--error);
  font-family: monospace;
  flex-shrink: 0;
  animation: tb-blink 1s step-start infinite;
}
@keyframes tb-blink { 50% { opacity: 0.4; } }

.tb-seek {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex: 1;
  min-width: 120px;
}
.tb-seek-slider {
  flex: 1;
  min-width: 0;
  accent-color: var(--accent);
  cursor: pointer;
  height: 4px;
}
.tb-seek-slider:disabled { cursor: default; opacity: 0.5; }

.tb-time {
  font-size: 0.68rem;
  font-family: monospace;
  font-variant-numeric: tabular-nums;
  color: var(--text-dim);
  flex-shrink: 0;
}

.tb-parts { display: flex; gap: 0.25rem; flex-shrink: 0; }

.tb-mute {
  background: var(--surface);
  border: 1px solid var(--surface-hover);
  border-radius: 4px;
  color: var(--text-dim);
  font-size: 0.6rem;
  font-weight: 700;
  cursor: pointer;
  min-width: 20px;
  padding: 0 4px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}
.tb-mute:hover { color: var(--text); }
.tb-mute.muted {
  background: var(--surface-muted);
  border-color: color-mix(in srgb, var(--accent) 33%, transparent);
  color: var(--text-faint);
  text-decoration: line-through;
}

.tb-volume { display: flex; align-items: center; gap: 0.35rem; flex-shrink: 0; }
.tb-vol-icon { font-size: 0.75rem; }
.tb-vol-slider { width: 90px; accent-color: var(--accent); cursor: pointer; }

@media (max-width: 900px) {
  .tb-label { display: none; }
  .tb-vol-slider { width: 60px; }
}
</style>
