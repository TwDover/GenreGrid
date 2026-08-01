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
      <button class="tb-btn" :disabled="isRecording || isIdle" @click="stop" title="Stop playback">■</button>
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

    <!-- Live playback tempo — non-destructive: sets transport speed only, never
         regenerates or re-exports. Only shown once a track is loaded. -->
    <div
      v-if="!isRecording && generatedBpm > 0"
      class="tb-tempo"
      :class="{ nudged: isTempoNudged }"
      :title="tempoTitle"
      @wheel.prevent="onTempoWheel"
    >
      <button class="tb-tempo-step" @click="nudgeBpm(-1)" title="Slower">−</button>
      <span class="tb-tempo-val">{{ Math.round(playbackBpm) }}<small>BPM</small></span>
      <button class="tb-tempo-step" @click="nudgeBpm(1)" title="Faster">+</button>
      <button
        v-if="isTempoNudged"
        class="tb-tempo-reset"
        @click="resetPlaybackBpm"
        :title="`Reset to generated ${Math.round(generatedBpm)} BPM`"
      >↺</button>
    </div>

    <!-- Instrument mode: sampled instruments vs full synthesis -->
    <div class="tb-mode" role="group" aria-label="Instrument sound">
      <button
        class="tb-mode-btn"
        :class="{ 'is-active': sampleMode === 'samples' }"
        :aria-pressed="sampleMode === 'samples'"
        title="Sampled instruments where available (piano, vibraphone), synth for the rest"
        @click="setSampleMode('samples')"
      >Samples</button>
      <button
        class="tb-mode-btn"
        :class="{ 'is-active': sampleMode === 'synth' }"
        :aria-pressed="sampleMode === 'synth'"
        title="Synthesize every instrument"
        @click="setSampleMode('synth')"
      >Synth</button>
    </div>
    <button
      v-if="instrumentsSupported()"
      class="tb-instr-btn"
      title="Manage custom instruments (upload your own samples)"
      @click="instrumentsPanelOpen = true"
    >🎹</button>
    <button
      class="tb-instr-btn"
      title="Design a synth voice"
      @click="openDesigner"
    >🎛</button>

    <!-- Metronome + count-in: a click to play/record against (meter-accented). -->
    <div v-if="!isRecording" class="tb-metro">
      <button
        class="tb-instr-btn tb-metro-btn"
        :class="{ 'is-on': metroEnabled }"
        :title="metroEnabled ? 'Metronome on — click' : 'Metronome — click along (accents the downbeat)'"
        @click="toggleMetronome"
      >♩</button>
      <button
        class="tb-instr-btn tb-metro-ci"
        :class="{ 'is-on': countInBars > 0 }"
        :title="countInTitle"
        @click="cycleCountIn"
      >{{ countInBars > 0 ? `${countInBars}·CI` : 'CI' }}</button>
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
import { useMidiPlayer } from '../composables/useMidiPlayer'
import { useCustomInstruments } from '../composables/useCustomInstruments'
import { useSynthDesigner } from '../composables/useSynthDesigner'
import { useMetronome } from '../composables/useMetronome'

const {
  currentlyPlaying, nowPlayingLabel, isLoading, isRecording,
  stop, looping, setLooping,
  positionSeconds, durationSeconds, seek, isPaused, playPause,
  volume, setVolume, sampleMode, setSampleMode, cuedLabel,
  generatedBpm, playbackBpm, isTempoNudged, setPlaybackBpm, resetPlaybackBpm,
} = useMidiPlayer()

const { panelOpen: instrumentsPanelOpen, supported: instrumentsSupported } = useCustomInstruments()
const { openDesigner } = useSynthDesigner()

const {
  enabled: metroEnabled, countInBars, setEnabled: setMetroEnabled, setCountInBars,
  startTicking: metroStartTicking, stopTicking: metroStopTicking, startStandalone: metroStartStandalone, stopStandalone: metroStopStandalone,
} = useMetronome()
function toggleMetronome() {
  const next = !metroEnabled.value
  setMetroEnabled(next)
  // While a track plays, the click rides the running transport; when idle, run the
  // transport just for the click (a standalone practice/tempo click).
  if (currentlyPlaying.value) {
    if (next) metroStartTicking(); else metroStopTicking()
  } else {
    if (next) metroStartStandalone(); else metroStopStandalone()
  }
}
const COUNT_IN_STEPS = [0, 1, 2]
function cycleCountIn() {
  const i = COUNT_IN_STEPS.indexOf(countInBars.value)
  setCountInBars(COUNT_IN_STEPS[(i + 1) % COUNT_IN_STEPS.length] ?? 0)
}
const countInTitle = computed(() =>
  countInBars.value > 0
    ? `Count-in: ${countInBars.value} bar${countInBars.value > 1 ? 's' : ''} of clicks before playback/recording`
    : 'Count-in: off — click to add a 1- or 2-bar lead-in before playback/recording',
)

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
  playPause()   // shared with the Space key (HomePage)
}

function fmt(s: number): string {
  const t = Math.max(0, Math.floor(s))
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, '0')}`
}

function onSeek(e: Event) {
  seek(+(e.target as HTMLInputElement).value)
}

function nudgeBpm(delta: number) {
  setPlaybackBpm(playbackBpm.value + delta)
}
function onTempoWheel(e: WheelEvent) {
  nudgeBpm(e.deltaY < 0 ? 1 : -1)
}

const tempoTitle = computed(() =>
  isTempoNudged.value
    ? `Playback tempo — generated ${Math.round(generatedBpm.value)} → ${Math.round(playbackBpm.value)} BPM (playback only, export unchanged)`
    : 'Playback tempo — nudge to feel it faster or slower without re-rolling',
)
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

/* Live playback-tempo control */
.tb-tempo {
  display: inline-flex;
  align-items: center;
  gap: 0.15rem;
  flex-shrink: 0;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 0 0.15rem;
  background: var(--surface);
}
.tb-tempo.nudged { border-color: var(--accent); background: var(--accent-surface-strong); }
.tb-tempo-step {
  width: 20px; height: 22px; line-height: 1;
  background: none; border: none; cursor: pointer;
  color: var(--text-faint); font-size: 0.9rem;
}
.tb-tempo-step:hover { color: var(--accent); }
.tb-tempo-val {
  min-width: 46px; text-align: center;
  font-size: 0.72rem; font-family: monospace; font-variant-numeric: tabular-nums;
  color: var(--text); cursor: ns-resize; user-select: none;
}
.tb-tempo.nudged .tb-tempo-val { color: var(--accent-bright); }
.tb-tempo-val small { font-size: 0.55em; margin-left: 1px; opacity: 0.6; }
.tb-tempo-reset {
  width: 18px; height: 22px; line-height: 1;
  background: none; border: none; cursor: pointer;
  color: var(--accent); font-size: 0.75rem;
}
.tb-tempo-reset:hover { filter: brightness(1.2); }

.tb-volume { display: flex; align-items: center; gap: 0.35rem; flex-shrink: 0; }
.tb-vol-icon { font-size: 0.75rem; }
.tb-vol-slider { width: 90px; accent-color: var(--accent); cursor: pointer; }

/* Samples/Synth segmented toggle */
.tb-mode { display: inline-flex; flex-shrink: 0; border: 1px solid var(--border); border-radius: 6px; overflow: hidden; }
.tb-mode-btn {
  font: inherit; font-size: 0.7rem; line-height: 1; padding: 0.3rem 0.5rem;
  background: var(--surface); color: var(--text-faint); border: none; cursor: pointer;
}
.tb-mode-btn + .tb-mode-btn { border-left: 1px solid var(--border); }
.tb-mode-btn:hover { color: var(--text); }
.tb-mode-btn.is-active { background: var(--accent); color: var(--accent-contrast, #fff); }
.tb-instr-btn {
  font-size: 0.85rem; line-height: 1; flex-shrink: 0; cursor: pointer;
  padding: 0.3rem 0.45rem; border: 1px solid var(--border); border-radius: 6px;
  background: var(--surface); color: var(--text-faint);
}
.tb-instr-btn:hover { color: var(--text); }
.tb-instr-btn:disabled { opacity: 0.5; cursor: default; }

/* Metronome + count-in */
.tb-metro { display: inline-flex; align-items: center; gap: 0.2rem; flex-shrink: 0; }
.tb-metro-btn { font-size: 1rem; }
.tb-metro-ci { font-size: 0.62rem; font-weight: 700; letter-spacing: 0.03em; }
.tb-metro-btn.is-on, .tb-metro-ci.is-on {
  border-color: var(--accent); background: var(--accent-surface-strong); color: var(--accent-bright);
}

@media (max-width: 900px) {
  .tb-label { display: none; }
  .tb-vol-slider { width: 60px; }
  .tb-mode, .tb-metro { display: none; }   /* keep the narrow bar uncluttered */
}
</style>
