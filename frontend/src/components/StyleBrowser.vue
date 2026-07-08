<!--
  GenreGrid — a style-based MIDI generator.
  Copyright (C) 2026 Tw Dover

  This program is free software: you can redistribute it and/or modify it under
  the terms of the GNU General Public License v3 or (at your option) any later
  version. Distributed WITHOUT ANY WARRANTY. See <https://www.gnu.org/licenses/>.
-->
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
          <div class="card-top">
            <span class="card-name">{{ style.name }}</span>
            <div class="card-actions">
              <button
                class="card-fav"
                :class="{ faved: favorites.has(style.id) }"
                @click.stop="toggleFavorite(style.id)"
                :title="favorites.has(style.id) ? 'Remove from favorites' : 'Add to favorites'"
              >{{ favorites.has(style.id) ? '★' : '☆' }}</button>
              <button
                class="card-play"
                :class="{ playing: isPlayingStyle(style.id) }"
                :disabled="isLoading && !isPlayingStyle(style.id)"
                @click.stop="togglePreview(style.id)"
                :title="isPlayingStyle(style.id) ? 'Stop preview' : 'Preview style'"
              >{{ isPlayingStyle(style.id) ? '■' : '▶' }}</button>
            </div>
          </div>
          <span class="card-bpm">{{ style.bpm_range[0] }}–{{ style.bpm_range[1] }} BPM</span>
          <span class="card-scale">{{ style.default_scale }}</span>
          <span class="card-desc">{{ STYLE_DESCRIPTIONS[style.id] ?? '' }}</span>
          <div class="card-audition">
            <button
              class="audition-btn"
              :class="{ playing: isAuditionPlaying(style) }"
              :disabled="auditioningId !== null && auditioningId !== style.id"
              @click.stop="toggleAudition(style)"
              :title="isAuditionPlaying(style) ? 'Stop audition' : 'Generate and play a 2-bar loop'"
            >
              <span v-if="auditioningId === style.id" class="audition-spinner"></span>
              <template v-else>{{ isAuditionPlaying(style) ? '■ stop' : '▶ audition' }}</template>
            </button>
            <span v-if="auditionErrors[style.id]" class="audition-error">{{ auditionErrors[style.id] }}</span>
          </div>
        </button>
      </div>

    </div>
  </div>
</template>

<script lang="ts">
// Session-scoped cache: style id → combined-file URL from a prior audition
// generate. Module-level so it survives the browser overlay being unmounted.
const auditionCache = new Map<string, string>()
</script>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { StyleInfo } from '../types/midi'
import { generate } from '../services/api'
import { useMidiPlayer } from '../composables/useMidiPlayer'

const props = defineProps<{ styles: StyleInfo[]; modelValue: string }>()
const emit = defineEmits<{
  (e: 'update:modelValue', id: string): void
  (e: 'close'): void
}>()

const STYLE_CATEGORIES: Record<string, string> = {
  house: 'Electronic', techno: 'Electronic', drum_and_bass: 'Electronic',
  synthwave: 'Electronic', future_bass: 'Electronic', jersey_club: 'Electronic',
  hyperpop: 'Electronic',
  lofi: 'Hip-hop', boom_bap: 'Hip-hop', dark_trap: 'Hip-hop', drill: 'Hip-hop',
  grime: 'Hip-hop', trap_soul: 'Hip-hop', cloud_rap: 'Hip-hop',
  jazz: 'Live', latin_jazz: 'Live', bossa_nova: 'Live',
  soul: 'Live', rnb: 'Live', funk: 'Live',
  afrobeats: 'Global', afropop: 'Global', samba: 'Global', cumbia: 'Global',
  reggaeton: 'Global', dancehall: 'Global', baile_funk: 'Global',
  cinematic: 'Mood', epic_orchestral: 'Mood',
  ambient: 'Mood', dark_ambient: 'Mood',
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

const ALL_CATS = 'All'
const categories = [ALL_CATS, 'Electronic', 'Hip-hop', 'Live', 'Global', 'Mood', 'Custom']

function categoryOf(style: StyleInfo): string {
  return style.custom ? 'Custom' : (STYLE_CATEGORIES[style.id] ?? ALL_CATS)
}

const activeCategory = ref((() => {
  if (!props.modelValue) return ALL_CATS
  const current = props.styles.find(s => s.id === props.modelValue)
  return current ? categoryOf(current) : (STYLE_CATEGORIES[props.modelValue] ?? ALL_CATS)
})())

const { toggle, currentlyPlaying, isLoading } = useMidiPlayer()

function previewUrl(styleId: string): string {
  return `/styles/${styleId}/preview`
}

function isPlayingStyle(styleId: string): boolean {
  return currentlyPlaying.value === previewUrl(styleId)
}

async function togglePreview(styleId: string) {
  await toggle(previewUrl(styleId), styleId, styleId.replace(/_/g, ' '))
}

// ── Favorites — persisted ids, sorted to the front of the grid ─────────────
const FAV_KEY = 'genregrid_fav_styles'

function loadFavorites(): Set<string> {
  try {
    const raw = localStorage.getItem(FAV_KEY)
    const ids = raw ? JSON.parse(raw) : []
    return new Set(Array.isArray(ids) ? ids.filter(id => typeof id === 'string') : [])
  } catch {
    return new Set()
  }
}

const favorites = ref<Set<string>>(loadFavorites())

function toggleFavorite(styleId: string) {
  const next = new Set(favorites.value)
  if (next.has(styleId)) next.delete(styleId)
  else next.add(styleId)
  favorites.value = next
  try { localStorage.setItem(FAV_KEY, JSON.stringify([...next])) } catch { /* storage unavailable */ }
}

const filteredStyles = computed(() => {
  const inCategory = activeCategory.value === ALL_CATS
    ? props.styles
    : props.styles.filter(s => categoryOf(s) === activeCategory.value)
  // Stable sort: favorites first, original backend order otherwise
  return [...inCategory].sort(
    (a, b) => Number(favorites.value.has(b.id)) - Number(favorites.value.has(a.id)),
  )
})

// ── One-click audition — generate a tiny loop and play its combined file ───
const auditioningId = ref<string | null>(null)
const auditionErrors = ref<Record<string, string>>({})

function isAuditionPlaying(style: StyleInfo): boolean {
  const url = auditionCache.get(style.id)
  return url !== undefined && currentlyPlaying.value === url
}

async function toggleAudition(style: StyleInfo) {
  const label = `${style.name} audition`
  const cached = auditionCache.get(style.id)
  if (cached) {
    // toggle() stops if this url is already playing, otherwise starts it
    await toggle(cached, style.id, label)
    return
  }

  auditioningId.value = style.id
  delete auditionErrors.value[style.id]
  try {
    const res = await generate({
      style_id: style.id,
      key: 'C',
      scale: style.default_scale,
      bpm: Math.round((style.bpm_range[0] + style.bpm_range[1]) / 2),
      bars: 2,
      complexity: 0.5,
      variation: 0.4,
      parts: ['chords', 'bass', 'melody', 'drums'],
      mode: 'loop',
      humanize: 0.5,
      blend_amount: 0.5,
      use_priors: false,
    })
    const combined = res.files.find(f => f.part === 'combined')
    if (!combined) throw new Error('No combined file returned')
    auditionCache.set(style.id, combined.url)
    await toggle(combined.url, style.id, label)
  } catch (e) {
    auditionErrors.value[style.id] = e instanceof Error ? e.message : 'Audition failed'
    setTimeout(() => { delete auditionErrors.value[style.id] }, 4000)
  } finally {
    auditioningId.value = null
  }
}

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
  background: var(--panel);
  border: 1px solid var(--surface);
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
  border-bottom: 1px solid var(--surface);
  flex-shrink: 0;
}

.browser-title {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text);
  letter-spacing: 0.04em;
}

.close-btn {
  background: none;
  border: none;
  color: var(--text-dim);
  font-size: 0.9rem;
  cursor: pointer;
  padding: 0.2rem 0.4rem;
  border-radius: 4px;
  transition: color 0.15s;
}
.close-btn:hover { color: var(--text); }

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
  background: var(--panel-deep);
  border: 1px solid var(--surface);
  border-radius: 20px;
  color: var(--text-dim);
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}
.cat-tab:hover { background: var(--panel-alt); color: var(--text); }
.cat-tab.active { background: var(--accent-surface); border-color: var(--accent); color: var(--accent-bright); }

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
  background: var(--panel-deep);
  border: 1px solid var(--surface);
  border-radius: 8px;
  cursor: pointer;
  text-align: left;
  transition: border-color 0.15s, background 0.15s;
}
.style-card:hover { background: var(--panel-alt); border-color: var(--surface-hover); }
.style-card.selected { border-color: var(--accent); background: var(--accent-surface); }

.card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.25rem;
}

.card-name {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text);
}

.card-actions {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  flex-shrink: 0;
}

.card-fav {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
  background: none;
  border: none;
  color: var(--text-faint);
  font-size: 0.8rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  transition: color 0.15s;
}
.card-fav:hover { color: var(--gold); }
.card-fav.faved { color: var(--gold); }

.card-play {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
  background: var(--surface);
  border: 1px solid var(--surface-hover);
  border-radius: 4px;
  color: var(--accent);
  font-size: 0.6rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  transition: background 0.15s;
}
.card-play:hover:not(:disabled) { background: var(--accent-surface-strong); }
.card-play.playing { background: var(--accent-surface-strong); border-color: var(--accent); }
.card-play:disabled { opacity: 0.5; cursor: not-allowed; }
.card-bpm {
  font-size: 0.65rem;
  color: var(--accent);
  font-family: monospace;
}
.card-scale {
  font-size: 0.62rem;
  color: var(--text-dim);
}
.card-desc {
  font-size: 0.65rem;
  color: var(--text-faint);
  line-height: 1.35;
  margin-top: 0.2rem;
}

.card-audition {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin-top: 0.35rem;
}

.audition-btn {
  font-size: 0.62rem;
  padding: 0.2rem 0.55rem;
  background: var(--surface);
  border: 1px solid var(--surface-hover);
  border-radius: 4px;
  color: var(--accent);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 4.5rem;
  min-height: 1.35rem;
  white-space: nowrap;
  transition: background 0.15s, border-color 0.15s;
}
.audition-btn:hover:not(:disabled) { background: var(--accent-surface-strong); }
.audition-btn.playing { background: var(--accent-surface-strong); border-color: var(--accent); }
.audition-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.audition-spinner {
  width: 10px;
  height: 10px;
  border: 2px solid var(--surface);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: audition-spin 0.7s linear infinite;
}
@keyframes audition-spin {
  to { transform: rotate(360deg); }
}

.audition-error {
  font-size: 0.6rem;
  color: var(--error);
  line-height: 1.3;
}

</style>
