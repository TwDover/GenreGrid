<template>
  <div class="part-card">
    <div class="part-header">
      <span class="part-name">{{ file.part }}</span>
      <span class="part-file">{{ file.filename }}</span>
    </div>
    <a :href="downloadHref" :download="file.filename" class="download-btn">
      Download .mid
    </a>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { FileInfo } from '../types/midi'
import { downloadUrl } from '../services/api'

const props = defineProps<{ file: FileInfo }>()
const downloadHref = computed(() => downloadUrl(props.file.url))
</script>
