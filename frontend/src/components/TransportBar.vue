<!--
  GenreGrid — a style-based MIDI generator.
  Copyright (C) 2026 Tw Dover

  This program is free software: you can redistribute it and/or modify it under
  the terms of the GNU General Public License v3 or (at your option) any later
  version. Distributed WITHOUT ANY WARRANTY. See <https://www.gnu.org/licenses/>.
-->
<template>
  <div v-if="isLoading || currentlyPlaying" class="transport-bar">
    <!-- Transport controls -->
    <div class="tb-controls">
      <button
        class="tb-btn tb-play"
        :disabled="isLoading || isRecording"
        @click="togglePause"
        :title="isPaused ? 'Resume' : 'Pause'"
      >{{ isLoading ? '⟳' : isPaused ? '▶' : '⏸' }}</button>
      <button class="tb-btn" :disabled="isRecording" @click="stop" title="Stop playback (Space)">■</button>
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
    <span v-else class="tb-label" :title="nowPlayingLabel ?? ''">{{ nowPlayingLabel ?? '…' }}</span>

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
import { useMidiPlayer, PLAYER_PARTS, type PlayerPart } from '../composables/useMidiPlayer'

const {
  currentlyPlaying, nowPlayingLabel, isLoading, isRecording,
  stop, looping, setLooping, channelMuted, toggleMute, soloPart,
  positionSeconds, durationSeconds, seek, isPaused, togglePause,
  volume, setVolume,
} = useMidiPlayer()

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
.transport-bar {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.4rem 1rem;
  background: #001523;
  border-bottom: 1px solid #00c8ff33;
  min-width: 0;
}

.tb-controls { display: flex; gap: 0.35rem; flex-shrink: 0; }

.tb-btn {
  width: 30px;
  height: 30px;
  background: #0d2535;
  border: 1px solid #122f40;
  border-radius: 6px;
  color: #00c8ff;
  font-size: 0.8rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
  transition: background 0.15s, border-color 0.15s;
}
.tb-btn:hover:not(:disabled) { background: #122f40; }
.tb-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.tb-btn.active { border-color: #00c8ff; background: #003450; }
.tb-play { background: #003450; }

.tb-label {
  font-size: 0.75rem;
  font-family: monospace;
  color: #7ae8ff;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 220px;
  flex-shrink: 1;
  text-transform: capitalize;
}

.tb-rec {
  font-size: 0.75rem;
  color: #f87171;
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
  accent-color: #00c8ff;
  cursor: pointer;
  height: 4px;
}
.tb-seek-slider:disabled { cursor: default; opacity: 0.5; }

.tb-time {
  font-size: 0.68rem;
  font-family: monospace;
  font-variant-numeric: tabular-nums;
  color: #4a7080;
  flex-shrink: 0;
}

.tb-parts { display: flex; gap: 0.25rem; flex-shrink: 0; }

.tb-mute {
  background: #0d2535;
  border: 1px solid #122f40;
  border-radius: 4px;
  color: #4a7080;
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
.tb-mute:hover { color: #e0e0e8; }
.tb-mute.muted {
  background: #001520;
  border-color: #00c8ff55;
  color: #2a4550;
  text-decoration: line-through;
}

.tb-volume { display: flex; align-items: center; gap: 0.35rem; flex-shrink: 0; }
.tb-vol-icon { font-size: 0.75rem; }
.tb-vol-slider { width: 90px; accent-color: #00c8ff; cursor: pointer; }

@media (max-width: 900px) {
  .tb-label { display: none; }
  .tb-vol-slider { width: 60px; }
}
</style>
