<template>
  <div class="browser-overlay" @click.self="$emit('close')">
    <div class="browser-panel">
      <div class="browser-header">
        <span class="browser-title">Choose a Style</span>
        <button class="close-btn" @click="$emit('close')">✕</button>
      </div>

      <div class="category-tabs">
        <button
          v-for="cat in categories"
          :key="cat"
          class="cat-tab"
          :class="{ active: activeCategory === cat }"
          @click="activeCategory = cat"
        >{{ cat }}</button>
      </div>

      <div class="style-grid">
        <button
          v-for="style in filteredStyles"
          :key="style.id"
          class="style-card"
          :class="{ selected: modelValue === style.id }"
          @click="select(style.id)"
        >
          <span class="card-name">{{ style.name }}</span>
          <span class="card-bpm">{{ style.bpm_range[0] }}–{{ style.bpm_range[1] }} BPM</span>
          <span class="card-scale">{{ style.default_scale }}</span>
          <span class="card-desc">{{ STYLE_DESCRIPTIONS[style.id] ?? '' }}</span>
        </button>
      </div>

      <div v-if="selectedDetail" class="selected-preview">
        <span class="preview-label">Style DNA</span>
        <StyleRadar :style="selectedDetail" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { StyleInfo } from '../types/midi'
import { fetchStyleDetail } from '../services/api'
import StyleRadar from './StyleRadar.vue'

const props = defineProps<{ styles: StyleInfo[]; modelValue: string }>()
const emit = defineEmits<{
  (e: 'update:modelValue', id: string): void
  (e: 'close'): void
}>()

const STYLE_CATEGORIES: Record<string, string> = {
  house: 'Electronic', techno: 'Electronic', drum_and_bass: 'Electronic',
  synthwave: 'Electronic', future_bass: 'Electronic', jersey_club: 'Electronic',
  hyperpop: 'Electronic',
  boom_bap: 'Hip-Hop', dark_trap: 'Hip-Hop', drill: 'Hip-Hop',
  trap_soul: 'Hip-Hop', cloud_rap: 'Hip-Hop', lofi: 'Hip-Hop', grime: 'Hip-Hop',
  rnb: 'Soul / R&B', soul: 'Soul / R&B', funk: 'Soul / R&B',
  afrobeats: 'Global', afropop: 'Global', dancehall: 'Global',
  reggaeton: 'Global', cumbia: 'Global', samba: 'Global', baile_funk: 'Global',
  latin_jazz: 'Latin / Jazz', bossa_nova: 'Latin / Jazz', jazz: 'Latin / Jazz',
  cinematic: 'Cinematic', epic_orchestral: 'Cinematic',
  ambient: 'Cinematic', dark_ambient: 'Cinematic',
}

const STYLE_DESCRIPTIONS: Record<string, string> = {
  house: 'Four-on-the-floor groove with lush pads and synth leads',
  techno: 'Hypnotic, industrial kick patterns and dark synths',
  drum_and_bass: 'Fast breakbeats over deep sub-bass lines',
  synthwave: 'Retro 80s arpeggios, lush chords, and saw leads',
  future_bass: 'Pitched vocal chops, supersaws, and trap-influenced hi-hats',
  jersey_club: 'Frenetic 808s, bouncy hi-hats, and call-and-response patterns',
  hyperpop: 'Distorted synths, pitched-up leads, and glitchy energy',
  boom_bap: 'Classic hip-hop swing with sampled-feel drums and walking bass',
  dark_trap: 'Sparse trap hi-hats, sub-808s, and minor-key menace',
  drill: 'Sliding 808s, heavy sub, and syncopated hi-hat rolls',
  trap_soul: 'Warm pads, melodic 808s, and slow-burn atmosphere',
  cloud_rap: 'Hazy, reverb-drenched atmospherics and slow triplet flow',
  lofi: 'Dusty vinyl textures, jazzy chords, and lazy swing',
  grime: 'Sharp synth stabs, rolling hi-hats, and gritty UK energy',
  rnb: 'Smooth Rhodes chords, pocket groove, and silky melody',
  soul: 'Warm organ, walking bass, and expressive brass melody',
  funk: 'Tight rhythm-guitar stabs, slap bass, and syncopated kicks',
  afrobeats: 'Afropop percussion patterns, bright guitar, and infectious rhythm',
  afropop: 'Buoyant West African melodic sensibility with modern production',
  dancehall: 'Riddim-style one-drop drums, bass synth, and reggae-influenced melody',
  reggaeton: 'Dembow rhythm, 808 bass, and Latin melodic hooks',
  cumbia: 'Colombian folk-rhythm guitar, bass, and lively flute melody',
  samba: 'Brazilian batucada percussion, nylon guitar, and ascending melody',
  baile_funk: 'Rio funk carioca — compressed synths, driving bass, and hot rhythm',
  latin_jazz: 'Clave-based rhythm, upright bass, and alto sax melody',
  bossa_nova: 'Gentle samba-jazz guitar comping, acoustic bass, and flute',
  jazz: 'Complex chord extensions, walking bass, and expressive sax lead',
  cinematic: 'Orchestral strings, french horn melody, and sweeping dynamics',
  epic_orchestral: 'Full orchestra, massive crescendos, and heroic brass',
  ambient: 'Slow-evolving pads, minimal rhythm, and textural melody',
  dark_ambient: 'Dissonant drones, sparse percussion, and eerie atmosphere',
}

const selectedDetail = ref<Record<string, any> | null>(null)

watch(() => props.modelValue, async (id) => {
  selectedDetail.value = null
  if (!id) return
  try {
    selectedDetail.value = await fetchStyleDetail(id)
  } catch {
    // silently ignore — radar just won't show
  }
}, { immediate: true })

const ALL_CATS = 'All'
const categories = [ALL_CATS, 'Electronic', 'Hip-Hop', 'Soul / R&B', 'Global', 'Latin / Jazz', 'Cinematic']
const activeCategory = ref(
  props.modelValue ? (STYLE_CATEGORIES[props.modelValue] ?? ALL_CATS) : ALL_CATS
)

const filteredStyles = computed(() =>
  activeCategory.value === ALL_CATS
    ? props.styles
    : props.styles.filter(s => STYLE_CATEGORIES[s.id] === activeCategory.value)
)

function select(id: string) {
  emit('update:modelValue', id)
  emit('close')
}
</script>

<style scoped>
.browser-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
  padding: 1rem;
}

.browser-panel {
  background: #060f14;
  border: 1px solid #0d2535;
  border-radius: 14px;
  width: min(700px, 100%);
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.browser-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.25rem 0.75rem;
  border-bottom: 1px solid #0d2535;
  flex-shrink: 0;
}

.browser-title {
  font-size: 0.85rem;
  font-weight: 600;
  color: #e0e0e8;
  letter-spacing: 0.04em;
}

.close-btn {
  background: none;
  border: none;
  color: #4a7080;
  font-size: 0.9rem;
  cursor: pointer;
  padding: 0.2rem 0.4rem;
  border-radius: 4px;
  transition: color 0.15s;
}
.close-btn:hover { color: #e0e0e8; }

.category-tabs {
  display: flex;
  gap: 0.25rem;
  padding: 0.75rem 1.25rem 0.5rem;
  overflow-x: auto;
  flex-shrink: 0;
  scrollbar-width: none;
}
.category-tabs::-webkit-scrollbar { display: none; }

.cat-tab {
  font-size: 0.72rem;
  padding: 0.25rem 0.75rem;
  background: #040a0e;
  border: 1px solid #0d2535;
  border-radius: 20px;
  color: #4a7080;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}
.cat-tab:hover { background: #081620; color: #e0e0e8; }
.cat-tab.active { background: #001e35; border-color: #00c8ff; color: #7ae8ff; }

.style-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 0.5rem;
  padding: 0.75rem 1.25rem 1.25rem;
  overflow-y: auto;
}

.style-card {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  padding: 0.65rem 0.8rem;
  background: #040a0e;
  border: 1px solid #0d2535;
  border-radius: 8px;
  cursor: pointer;
  text-align: left;
  transition: border-color 0.15s, background 0.15s;
}
.style-card:hover { background: #081620; border-color: #1a4560; }
.style-card.selected { border-color: #00c8ff; background: #001e35; }

.card-name {
  font-size: 0.85rem;
  font-weight: 600;
  color: #e0e0e8;
}
.card-bpm {
  font-size: 0.65rem;
  color: #00c8ff;
  font-family: monospace;
}
.card-scale {
  font-size: 0.62rem;
  color: #4a7080;
}
.card-desc {
  font-size: 0.65rem;
  color: #2a4550;
  line-height: 1.35;
  margin-top: 0.2rem;
}

.selected-preview {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.4rem;
  padding: 0.75rem 1.25rem;
  background: #040a0e;
  border-top: 1px solid #0d2535;
}

.preview-label {
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #2a4550;
}
</style>
