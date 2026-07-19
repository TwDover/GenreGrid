<!--
  GenreGrid — a style-based MIDI generator.
  Copyright (C) 2026 Tw Dover

  This program is free software: you can redistribute it and/or modify it under
  the terms of the GNU General Public License v3 or (at your option) any later
  version. Distributed WITHOUT ANY WARRANTY. See <https://www.gnu.org/licenses/>.
-->
<!--
  Compare-and-keep picker (roadmap-2 item 7): shows the rolled candidate
  variations of one part as mini piano-rolls the user can audition, then keep
  one. The others are discarded server-side when a keep commits.
-->
<template>
  <div class="cp">
    <div class="cp-head">
      <span class="cp-title">Pick a {{ part.replace('_', ' ') }} — {{ candidates.length }} rolls</span>
      <button class="cp-close" @click="$emit('cancel')" :disabled="keeping !== null">✕ cancel</button>
    </div>
    <div class="cp-grid">
      <div v-for="c in candidates" :key="c.index" class="cp-card" :class="{ 'cp-playing': isPlaying(c.url) }">
        <div class="cp-roll">
          <PianoRoll
            v-if="midi(c.url)"
            :notes="midi(c.url)!.notes"
            :duration="midi(c.url)!.duration"
            :playing="isPlaying(c.url)"
            :keyRoot="keyRoot"
            :scale="scale"
          />
          <div v-else class="cp-roll-empty">loading…</div>
        </div>
        <div class="cp-actions">
          <button class="cp-btn" @click="play(c.url)" :title="isPlaying(c.url) ? 'Stop' : 'Preview'">
            {{ isPlaying(c.url) ? '■' : '▶' }} {{ c.index + 1 }}
          </button>
          <button class="cp-keep" :disabled="keeping !== null" @click="$emit('keep', c.index)">
            {{ keeping === c.index ? '…' : 'Keep' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onBeforeUnmount, watch } from 'vue'
import type { SongPartCandidate } from '../services/api'
import { useMidiPlayer } from '../composables/useMidiPlayer'
import PianoRoll from './PianoRoll.vue'

const props = defineProps<{
  candidates: SongPartCandidate[]
  part: string
  styleId?: string
  keyRoot?: string
  scale?: string
  keeping: number | null   // index currently being committed
}>()

defineEmits<{ (e: 'keep', index: number): void; (e: 'cancel'): void }>()

const { getMidiData, prefetchMidi, toggle, stop, currentlyPlaying } = useMidiPlayer()

const midi = (url: string) => getMidiData(url)
const isPlaying = (url: string) => currentlyPlaying.value === url

async function warm() {
  for (const c of props.candidates) await prefetchMidi(c.url)
}
onMounted(warm)
watch(() => props.candidates.map(c => c.url).join(','), warm)
onBeforeUnmount(() => { if (currentlyPlaying.value) stop() })

function play(url: string) {
  if (isPlaying(url)) { stop(); return }
  toggle(url, props.styleId, `${props.part} candidate`)
}
</script>

<style scoped>
.cp {
  border: 1px solid color-mix(in srgb, var(--accent) 33%, transparent);
  background: var(--panel-deep); border-radius: 8px; padding: 0.6rem; display: flex;
  flex-direction: column; gap: 0.5rem;
}
.cp-head { display: flex; align-items: center; justify-content: space-between; }
.cp-title { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--accent); }
.cp-close {
  font-size: 0.68rem; background: transparent; border: none; color: var(--text-faint);
  cursor: pointer;
}
.cp-close:hover:not(:disabled) { color: var(--text); }
.cp-close:disabled { opacity: 0.5; cursor: wait; }
.cp-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 0.5rem; }
.cp-card {
  display: flex; flex-direction: column; gap: 0.35rem;
  border: 1px solid var(--surface); border-radius: 6px; padding: 0.4rem; background: var(--panel);
  transition: border-color 0.15s;
}
.cp-card.cp-playing { border-color: var(--accent); }
.cp-roll { height: 56px; }
.cp-roll-empty {
  height: 56px; display: flex; align-items: center; justify-content: center;
  font-size: 0.62rem; color: var(--text-faint); background: var(--panel-deep); border-radius: 4px;
}
.cp-actions { display: flex; gap: 0.35rem; }
.cp-btn {
  flex: 1; font-size: 0.72rem; padding: 0.3rem; border-radius: 5px; cursor: pointer;
  background: var(--surface); border: 1px solid var(--surface-hover); color: var(--accent);
}
.cp-btn:hover { background: var(--surface-hover); }
.cp-keep {
  flex: 1; font-size: 0.72rem; padding: 0.3rem; border-radius: 5px; cursor: pointer;
  background: var(--accent-surface-strong); border: 1px solid color-mix(in srgb, var(--accent) 45%, transparent);
  color: var(--accent);
}
.cp-keep:hover:not(:disabled) { background: var(--accent-surface); }
.cp-keep:disabled { opacity: 0.5; cursor: wait; }
</style>
