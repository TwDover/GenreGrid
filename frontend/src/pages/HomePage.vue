<template>
  <div class="home-page">
    <header class="app-header">
      <h1>GenreGrid</h1>
      <p class="subtitle">Style-based MIDI generator</p>
    </header>

    <main class="app-main">
      <section class="form-section">
        <GenerateForm :styles="styles" :loading="loading" @submit="handleGenerate" />
        <p v-if="error" class="error-msg">{{ error }}</p>
      </section>

      <section class="export-section">
        <ExportPanel :response="result" />
      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import GenerateForm from '../components/GenerateForm.vue'
import ExportPanel from '../components/ExportPanel.vue'
import { fetchStyles, generate } from '../services/api'
import type { StyleInfo, GenerateRequest, GenerateResponse } from '../types/midi'

const styles = ref<StyleInfo[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const result = ref<GenerateResponse | null>(null)

onMounted(async () => {
  try {
    styles.value = await fetchStyles()
  } catch (e) {
    error.value = 'Could not reach backend — make sure uvicorn is running on port 8000.'
  }
})

async function handleGenerate(form: GenerateRequest) {
  loading.value = true
  error.value = null
  result.value = null
  try {
    result.value = await generate(form)
  } catch (e: any) {
    error.value = e.message ?? 'Unknown error'
  } finally {
    loading.value = false
  }
}
</script>
