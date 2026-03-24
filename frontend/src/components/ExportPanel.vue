<template>
  <div v-if="response" class="export-panel">
    <div class="export-summary">
      <span>{{ response.summary.key }}</span>
      <span>{{ response.summary.bpm }} BPM</span>
      <span>{{ response.summary.bars }} bars</span>
      <span class="gen-id">ID: {{ response.generation_id }}</span>
    </div>
    <div class="part-cards">
      <PartCard v-for="file in response.files" :key="file.part" :file="file" />
    </div>
  </div>
</template>

<script setup lang="ts">
import PartCard from './PartCard.vue'
import type { GenerateResponse } from '../types/midi'

defineProps<{ response: GenerateResponse | null }>()
</script>
