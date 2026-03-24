<template>
  <div class="field">
    <label>Style</label>
    <select :value="modelValue" @change="$emit('update:modelValue', ($event.target as HTMLSelectElement).value)">
      <option v-if="styles.length === 0" disabled value="">Loading...</option>
      <option v-for="s in styles" :key="s.id" :value="s.id">{{ s.name }}</option>
    </select>
  </div>
</template>

<script setup lang="ts">
import type { StyleInfo } from '../types/midi'

defineProps<{
  modelValue: string
  styles: StyleInfo[]
}>()
defineEmits<{ (e: 'update:modelValue', value: string): void }>()
</script>
