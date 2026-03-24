<template>
  <div class="part-card" :class="{ playing }">
    <div class="part-header">
      <span class="part-name">{{ file.part }}</span>
      <span class="part-file">{{ file.filename }}</span>
    </div>
    <div class="card-actions">
      <button class="play-btn" :disabled="isLoading" @click="toggle(file.url, styleId)" :title="playing ? 'Stop' : 'Preview'">
        <span v-if="isLoading && !playing">...</span>
        <span v-else>{{ playing ? '■' : '▶' }}</span>
      </button>
      <a :href="downloadHref" :download="file.filename" class="download-btn">
        Download .mid
      </a>
    </div>
    <PianoRoll
      v-if="midiData"
      :notes="midiData.notes"
      :duration="midiData.duration"
      :playing="playing"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { FileInfo } from '../types/midi'
import { downloadUrl } from '../services/api'
import { useMidiPlayer } from '../composables/useMidiPlayer'
import PianoRoll from './PianoRoll.vue'

const props = defineProps<{ file: FileInfo; styleId?: string }>()
const downloadHref = computed(() => downloadUrl(props.file.url))

const { toggle, currentlyPlaying, isLoading, getMidiData } = useMidiPlayer()
const playing = computed(() => currentlyPlaying.value === props.file.url)
const midiData = computed(() => getMidiData(props.file.url))
</script>

<style scoped>
.card-actions {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}

.play-btn {
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  background: #2a2a3e;
  border: 1px solid #3a3a54;
  border-radius: 6px;
  color: #a78bfa;
  font-size: 0.9rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s;
}
.play-btn:hover:not(:disabled) { background: #3a3a54; }
.play-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.playing .play-btn {
  background: #3b1f6e;
  border-color: #a78bfa;
}

.playing {
  border-color: #a78bfa;
}
</style>
