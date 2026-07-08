<!--
  GenreGrid — a style-based MIDI generator.
  Copyright (C) 2026 Tw Dover

  This program is free software: you can redistribute it and/or modify it under
  the terms of the GNU General Public License v3 or (at your option) any later
  version. Distributed WITHOUT ANY WARRANTY. See <https://www.gnu.org/licenses/>.
-->
<template>
  <div class="song-form">
    <!-- Template Picker -->
    <div class="sb-section">
      <label class="sb-label">Template</label>
      <div class="template-grid">
        <button
          v-for="tpl in templates"
          :key="tpl.id"
          class="tpl-card"
          :class="{ active: form.template === tpl.id }"
          @click="form.template = tpl.id"
        >
          <span class="tpl-name">{{ tpl.label }}</span>
          <span class="tpl-bars">~{{ tpl.totalBars }}b</span>
          <div class="tpl-strip">
            <span
              v-for="sec in tpl.sections"
              :key="sec.name"
              class="tpl-seg"
              :class="`seg-${sec.type}`"
              :style="{ flex: sec.bars }"
              :title="sec.name"
            />
          </div>
        </button>
        <button
          class="tpl-card"
          :class="{ active: form.template === 'custom' }"
          @click="form.template = 'custom'"
        >
          <span class="tpl-name">Custom</span>
          <span class="tpl-bars">~{{ customTotalBars }}b</span>
          <div class="tpl-strip">
            <span
              v-for="(sec, i) in customSections"
              :key="i"
              class="tpl-seg"
              :class="`seg-${sec.section_type}`"
              :style="{ flex: sec.bars }"
              :title="sec.section_type"
            />
          </div>
        </button>
      </div>

      <!-- Custom template editor -->
      <div v-if="form.template === 'custom'" class="custom-editor">
        <div v-for="(sec, i) in customSections" :key="i" class="ce-row">
          <select v-model="sec.section_type" class="sb-select ce-type">
            <option v-for="t in SECTION_TYPES" :key="t" :value="t">{{ t.replace('_', ' ') }}</option>
          </select>
          <input v-model.number="sec.bars" type="number" min="1" max="32" class="sb-input ce-bars" />
          <select v-model="sec.style_id" class="sb-select ce-style" title="Optional per-section style">
            <option value="">song style</option>
            <option v-for="s in styles" :key="s.id" :value="s.id">{{ s.name }}</option>
          </select>
          <button class="ce-btn" :disabled="i === 0" @click="moveSection(i, -1)" title="Move up">↑</button>
          <button class="ce-btn" :disabled="i === customSections.length - 1" @click="moveSection(i, 1)" title="Move down">↓</button>
          <button class="ce-btn ce-del" :disabled="customSections.length <= 1" @click="customSections.splice(i, 1)" title="Remove">✕</button>
        </div>
        <button class="ce-add" :disabled="customSections.length >= 20" @click="customSections.push({ section_type: 'verse', bars: 8, style_id: '' })">＋ section</button>
      </div>
    </div>

    <!-- Style + Key row -->
    <div class="sb-row">
      <div class="sb-field">
        <label class="sb-label">Style</label>
        <select v-model="form.style_id" class="sb-select">
          <option v-for="s in styles" :key="s.id" :value="s.id">{{ s.name }}</option>
        </select>
      </div>
      <div class="sb-field sb-field-sm">
        <label class="sb-label">Key</label>
        <select v-model="form.key" class="sb-select">
          <option v-for="k in keys" :key="k" :value="k">{{ k }}</option>
        </select>
      </div>
      <div class="sb-field sb-field-sm">
        <label class="sb-label">Scale</label>
        <select v-model="form.scale" class="sb-select">
          <option value="major">Major</option>
          <option value="minor">Minor</option>
          <option value="dorian">Dorian</option>
          <option value="phrygian">Phrygian</option>
          <option value="mixolydian">Mixolydian</option>
          <option value="pentatonic_minor">Penta Minor</option>
          <option value="pentatonic_major">Penta Major</option>
          <option value="blues">Blues</option>
          <option value="harmonic_minor">Harm. Minor</option>
        </select>
      </div>
      <div class="sb-field sb-field-sm">
        <label class="sb-label">BPM <span v-if="selectedStyle" class="sb-val">{{ selectedStyle.bpm_range[0] }}–{{ selectedStyle.bpm_range[1] }}</span></label>
        <input type="number" v-model.number="form.bpm"
               :min="selectedStyle?.bpm_range[0] ?? 40"
               :max="selectedStyle?.bpm_range[1] ?? 240"
               class="sb-input" />
      </div>
      <div class="sb-field sb-field-sm">
        <label class="sb-label">Chorus <span class="sb-val" title="Transpose chorus sections for a lift">key</span></label>
        <select v-model.number="form.chorus_key_shift" class="sb-select">
          <option :value="0">none</option>
          <option :value="1">+1 (½ step)</option>
          <option :value="2">+2 (whole)</option>
          <option :value="3">+3</option>
          <option :value="5">+5 (4th)</option>
          <option :value="-2">−2</option>
          <option :value="-5">−5</option>
        </select>
      </div>
      <div class="sb-field sb-field-sm">
        <label class="sb-label">Final <span class="sb-val" title="Extra semitone lift on the last chorus only — the classic gear change">lift</span></label>
        <select v-model.number="form.final_chorus_lift" class="sb-select">
          <option :value="0">none</option>
          <option :value="1">+1</option>
          <option :value="2">+2</option>
        </select>
      </div>
    </div>

    <!-- Complexity / Variation -->
    <div class="sb-row">
      <div class="sb-field">
        <label class="sb-label">Complexity <span class="sb-val">{{ form.complexity.toFixed(2) }}</span></label>
        <input type="range" v-model.number="form.complexity" min="0" max="1" step="0.01" class="sb-range" />
      </div>
      <div class="sb-field">
        <label class="sb-label">Variation <span class="sb-val">{{ form.variation.toFixed(2) }}</span></label>
        <input type="range" v-model.number="form.variation" min="0" max="1" step="0.01" class="sb-range" />
      </div>
    </div>

    <!-- Style blend -->
    <div class="sb-row">
      <div class="sb-field">
        <label class="sb-label">Blend with <span class="sb-val">optional second style</span></label>
        <select v-model="form.blend_style_id" class="sb-select">
          <option value="">none</option>
          <option v-for="s in styles.filter(s => s.id !== form.style_id)" :key="s.id" :value="s.id">{{ s.name }}</option>
        </select>
      </div>
      <div class="sb-field" v-if="form.blend_style_id">
        <label class="sb-label">Blend amount <span class="sb-val">{{ form.blend_amount.toFixed(2) }}</span></label>
        <input type="range" v-model.number="form.blend_amount" min="0" max="1" step="0.05" class="sb-range" />
      </div>
    </div>

    <!-- Parts -->
    <div class="sb-field">
      <label class="sb-label">Parts</label>
      <div class="sb-parts">
        <label v-for="p in allParts" :key="p" class="sb-part-toggle">
          <input type="checkbox" :value="p" v-model="form.parts" />
          <span>{{ p }}</span>
        </label>
      </div>
    </div>

    <!-- Learned-patterns toggle (only for styles with a mined prior) -->
    <div class="sb-field" v-if="selectedStyle?.has_prior">
      <label class="sb-prior-toggle">
        <input type="checkbox" v-model="form.use_priors" />
        <span>Use my local MIDI corpus <span class="sb-val">optional — overlays patterns mined from a corpus you provide on top of the built-in ones; you're responsible for its license</span></span>
      </label>
    </div>

    <!-- Build around my melody -->
    <div class="sb-field">
      <label class="sb-label">Build around my melody <span class="sb-val">optional — drop a MIDI melody and it becomes the song's hook (key auto-detected)</span></label>
      <div class="sb-melody-row">
        <input ref="melodyInput" type="file" accept=".mid,.midi" class="sb-melody-file" @change="onMelodyFile" />
        <button v-if="melodyFile" class="sb-melody-clear" @click="clearMelodyFile" title="Remove file">✕</button>
      </div>
    </div>

    <!-- Generate Button -->
    <button class="sb-generate-btn" :disabled="loading || form.parts.length === 0" @click="generate">
      <span v-if="loading" class="sb-spinner">●</span>
      <span v-if="loading">Building song…</span>
      <span v-else-if="melodyFile">▶ Build Song Around My Melody</span>
      <span v-else>▶ Build Full Song</span>
    </button>
    <div v-if="error" class="sb-error">{{ error }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { StyleInfo, BuildSongResponse } from '../types/midi'
import { buildSong, buildSongFromMelody } from '../services/api'

const props = defineProps<{ styles: StyleInfo[] }>()
const emit = defineEmits<{
  (e: 'built', result: BuildSongResponse, label: string): void
  (e: 'building', v: boolean): void
}>()

const keys = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
const allParts = ['chords', 'bass', 'melody', 'drums', 'arpeggio', 'pads', 'counter_melody']

interface TemplateSection { name: string; bars: number; type: string }
interface TemplateOption { id: string; label: string; totalBars: number; sections: TemplateSection[] }

const templates: TemplateOption[] = [
  {
    id: 'verse_chorus', label: 'Verse–Chorus', totalBars: 56,
    sections: [
      { name: 'Intro', bars: 4, type: 'intro' }, { name: 'Verse', bars: 16, type: 'verse' },
      { name: 'Chorus', bars: 8, type: 'chorus' }, { name: 'Verse 2', bars: 16, type: 'verse' },
      { name: 'Chorus 2', bars: 8, type: 'chorus' }, { name: 'Outro', bars: 4, type: 'outro' },
    ],
  },
  {
    id: 'verse_chorus_bridge', label: 'V–C–Bridge', totalBars: 80,
    sections: [
      { name: 'Intro', bars: 4, type: 'intro' }, { name: 'Verse', bars: 16, type: 'verse' },
      { name: 'Pre-Chorus', bars: 4, type: 'pre_chorus' }, { name: 'Chorus', bars: 8, type: 'chorus' },
      { name: 'Verse 2', bars: 16, type: 'verse' }, { name: 'Pre-Chorus 2', bars: 4, type: 'pre_chorus' },
      { name: 'Chorus 2', bars: 8, type: 'chorus' }, { name: 'Bridge', bars: 8, type: 'bridge' },
      { name: 'Final Chorus', bars: 8, type: 'chorus' }, { name: 'Outro', bars: 4, type: 'outro' },
    ],
  },
  {
    id: 'extended', label: 'Extended', totalBars: 80,
    sections: [
      { name: 'Intro', bars: 4, type: 'intro' }, { name: 'Verse', bars: 16, type: 'verse' },
      { name: 'Chorus', bars: 8, type: 'chorus' }, { name: 'Verse 2', bars: 16, type: 'verse' },
      { name: 'Chorus 2', bars: 8, type: 'chorus' }, { name: 'Instrumental', bars: 8, type: 'instrumental_solo' },
      { name: 'Bridge', bars: 8, type: 'bridge' }, { name: 'Final Chorus', bars: 8, type: 'chorus' },
      { name: 'Outro', bars: 4, type: 'outro' },
    ],
  },
  {
    id: 'compact', label: 'Compact', totalBars: 40,
    sections: [
      { name: 'Intro', bars: 4, type: 'intro' }, { name: 'Verse', bars: 8, type: 'verse' },
      { name: 'Chorus', bars: 8, type: 'chorus' }, { name: 'Verse 2', bars: 8, type: 'verse' },
      { name: 'Chorus 2', bars: 8, type: 'chorus' }, { name: 'Outro', bars: 4, type: 'outro' },
    ],
  },
  {
    id: 'minimal', label: 'Minimal', totalBars: 24,
    sections: [
      { name: 'Intro', bars: 4, type: 'intro' }, { name: 'Main', bars: 16, type: 'verse' },
      { name: 'Outro', bars: 4, type: 'outro' },
    ],
  },
]

const form = ref({
  style_id: props.styles[0]?.id ?? '',
  key: 'C',
  scale: 'minor',
  bpm: 120,
  complexity: 0.6,
  variation: 0.4,
  humanize: 0.5,
  // Pads default on: they only sound in choruses/bridges and are the cheapest
  // "full arrangement" win — untick to drop them.
  parts: ['chords', 'bass', 'melody', 'drums', 'pads'],
  template: 'verse_chorus',
  use_priors: false,
  chorus_key_shift: 0,
  final_chorus_lift: 1,
  blend_style_id: '' as string,
  blend_amount: 0.5,
})

// Custom template editor state — seeded with a sensible starting arrangement.
const SECTION_TYPES = ['intro', 'verse', 'pre_chorus', 'chorus', 'post_chorus', 'bridge', 'instrumental_solo', 'outro']
const customSections = ref<{ section_type: string; bars: number; style_id?: string }[]>([
  { section_type: 'intro', bars: 4, style_id: '' },
  { section_type: 'verse', bars: 8, style_id: '' },
  { section_type: 'chorus', bars: 8, style_id: '' },
  { section_type: 'outro', bars: 4, style_id: '' },
])
const customTotalBars = computed(() => customSections.value.reduce((n, s) => n + s.bars, 0))

function moveSection(i: number, dir: number) {
  const j = i + dir
  const arr = customSections.value
  ;[arr[i], arr[j]] = [arr[j], arr[i]]
}

// Sensible defaults per section type when building a custom template payload
const CUSTOM_PARTS_MODE: Record<string, string> = {
  intro: 'melodic', verse: 'no_arp', pre_chorus: 'sparse', chorus: 'full',
  post_chorus: 'full', bridge: 'full', instrumental_solo: 'full', outro: 'melodic',
}

const selectedStyle = computed(() => props.styles.find(s => s.id === form.value.style_id))
const templateLabel = computed(() => templates.find(t => t.id === form.value.template)?.label ?? form.value.template)

// Selecting a style adopts its typical BPM (midpoint of its range) and its
// default scale — also on first load, so the form always matches the style
// shown in the dropdown.
watch(selectedStyle, (style) => {
  if (!style) return
  const [min, max] = style.bpm_range
  form.value.bpm = Math.round((min + max) / 2)
  if (style.default_scale) form.value.scale = style.default_scale
}, { immediate: true })

const loading = ref(false)
const error = ref<string | null>(null)

// ── Melody import ────────────────────────────────────────────────────────────
const melodyInput = ref<HTMLInputElement | null>(null)
const melodyFile = ref<File | null>(null)

function onMelodyFile(e: Event) {
  melodyFile.value = (e.target as HTMLInputElement).files?.[0] ?? null
}
function clearMelodyFile() {
  melodyFile.value = null
  if (melodyInput.value) melodyInput.value.value = ''
}

async function generate() {
  loading.value = true
  error.value = null
  emit('building', true)
  try {
    if (melodyFile.value) {
      // Key/scale/BPM come from the uploaded melody — the form's are ignored.
      const result = await buildSongFromMelody(melodyFile.value, {
        style_id: form.value.style_id,
        template: form.value.template === 'custom' ? 'verse_chorus' : form.value.template,
        parts: form.value.parts,
        complexity: form.value.complexity,
        variation: form.value.variation,
        humanize: form.value.humanize,
        use_priors: form.value.use_priors,
        chorus_key_shift: form.value.chorus_key_shift,
        final_chorus_lift: form.value.final_chorus_lift,
      })
      emit('built', result, `${templateLabel.value} (your melody)`)
      return
    }
    const payload: any = { ...form.value }
    if (!payload.blend_style_id) delete payload.blend_style_id
    if (form.value.template === 'custom') {
      payload.custom_template = customSections.value.map((s, i) => ({
        section_type: s.section_type,
        bars: s.bars,
        name: `${s.section_type.replace('_', ' ')} ${i + 1}`,
        parts_mode: CUSTOM_PARTS_MODE[s.section_type] ?? 'full',
        chorus_key: s.section_type === 'chorus',
        bridge_key: s.section_type === 'bridge',
        style_id: s.style_id || undefined,
      }))
    }
    const result = await buildSong(payload)
    emit('built', result, templateLabel.value)
  } catch (e: any) {
    error.value = e.message ?? 'Song generation failed'
  } finally {
    loading.value = false
    emit('building', false)
  }
}
</script>

<style scoped>
.song-form { display: flex; flex-direction: column; gap: 0.75rem; }

.sb-section { display: flex; flex-direction: column; gap: 0.35rem; }
.sb-label { font-size: 0.68rem; color: var(--text-dim); font-weight: 500; display: flex; align-items: center; gap: 0.4rem; }
.sb-val { color: var(--accent); font-family: monospace; }

/* Template cards */
.template-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 0.35rem; }
.tpl-card {
  background: var(--panel-deep); border: 1px solid var(--surface); border-radius: 6px;
  padding: 0.4rem 0.5rem 0.35rem; cursor: pointer; display: flex;
  flex-direction: column; gap: 0.25rem; text-align: left;
  transition: border-color 0.15s, background 0.15s;
}
.tpl-card:hover { border-color: #1a4060; background: var(--panel-alt); }
.tpl-card.active { border-color: color-mix(in srgb, var(--accent) 40%, transparent); background: var(--accent-surface); }
.tpl-name { font-size: 0.7rem; font-weight: 600; color: var(--text-soft); }
.tpl-bars { font-size: 0.6rem; font-family: monospace; color: var(--text-faint); }
.tpl-strip { display: flex; height: 6px; border-radius: 3px; overflow: hidden; gap: 1px; }
.tpl-seg { min-width: 2px; border-radius: 1px; }

/* Row / field layout */
.sb-row { display: flex; gap: 0.6rem; align-items: flex-end; flex-wrap: wrap; }
.sb-field { display: flex; flex-direction: column; gap: 0.2rem; flex: 1; min-width: 120px; }
.sb-field-sm { flex: 0 0 auto; min-width: 72px; }

.sb-select, .sb-input {
  background: var(--panel-deep); border: 1px solid var(--surface); border-radius: 5px;
  color: var(--text-soft); font-size: 0.75rem; padding: 0.28rem 0.45rem;
  width: 100%; box-sizing: border-box;
}
.sb-select:focus, .sb-input:focus { outline: none; border-color: color-mix(in srgb, var(--accent) 27%, transparent); }
.sb-range { width: 100%; accent-color: var(--accent); cursor: pointer; }

/* Parts toggles */
.sb-parts { display: flex; flex-wrap: wrap; gap: 0.35rem; }
.sb-part-toggle { display: flex; align-items: center; gap: 0.25rem; font-size: 0.72rem; color: var(--text-dim); cursor: pointer; }
.sb-part-toggle input { accent-color: var(--accent); cursor: pointer; }
.sb-part-toggle:hover span { color: var(--text-soft); }

.sb-prior-toggle { display: flex; align-items: center; gap: 0.4rem; font-size: 0.78rem; color: var(--text-dim); cursor: pointer; }
.sb-prior-toggle input { accent-color: var(--accent); cursor: pointer; }
.sb-prior-toggle .sb-val { margin-left: 0.35rem; color: var(--text-dim); font-size: 0.7rem; }

/* Generate button */
.sb-generate-btn {
  padding: 0.55rem 1rem; background: var(--accent-surface); border: 1px solid color-mix(in srgb, var(--accent) 33%, transparent);
  border-radius: 7px; color: var(--accent); font-size: 0.82rem; font-weight: 600;
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  gap: 0.4rem; transition: background 0.15s, border-color 0.15s;
}
.sb-generate-btn:hover:not(:disabled) { background: var(--accent-surface-strong); border-color: var(--accent); }
.sb-generate-btn:disabled { opacity: 0.5; cursor: default; }
.sb-spinner { animation: spin 1s linear infinite; display: inline-block; }
@keyframes spin { to { transform: rotate(360deg); } }

.sb-error { font-size: 0.72rem; color: var(--error); background: var(--error-surface); border-radius: 4px; padding: 0.3rem 0.5rem; }

/* Section type colors (template preview strips) */
.seg-intro { background: var(--seg-intro); }
.seg-verse { background: var(--seg-verse); }
.seg-pre_chorus { background: var(--seg-pre_chorus); }
.seg-chorus { background: var(--seg-chorus); }
.seg-post_chorus { background: var(--seg-post_chorus); }
.seg-bridge { background: var(--seg-bridge); }
.seg-instrumental_solo { background: var(--seg-instrumental_solo); }
.seg-outro { background: var(--seg-outro); }

/* Custom template editor */
.custom-editor { display: flex; flex-direction: column; gap: 0.3rem; margin-top: 0.5rem; }
.ce-row { display: flex; align-items: center; gap: 0.3rem; }
.ce-type { flex: 1; min-width: 0; }
.ce-bars { width: 56px; flex-shrink: 0; }
.ce-style { flex: 1; min-width: 0; opacity: 0.85; }
.ce-btn {
  width: 24px; height: 24px; flex-shrink: 0; padding: 0;
  background: var(--surface); border: 1px solid var(--surface-hover); border-radius: 4px;
  color: var(--text-dim); font-size: 0.7rem; cursor: pointer; line-height: 1;
}
.ce-btn:hover:not(:disabled) { color: var(--accent); }
.ce-btn:disabled { opacity: 0.35; cursor: not-allowed; }
.ce-del:hover:not(:disabled) { color: var(--error); }
.ce-add {
  align-self: flex-start; font-size: 0.7rem; padding: 0.25rem 0.6rem;
  background: transparent; border: 1px dashed var(--surface); border-radius: 5px;
  color: var(--text-dim); cursor: pointer;
}
.ce-add:hover:not(:disabled) { border-color: color-mix(in srgb, var(--accent) 40%, transparent); color: var(--accent); }
.ce-add:disabled { opacity: 0.4; cursor: not-allowed; }

/* Melody import */
.sb-melody-row { display: flex; align-items: center; gap: 0.4rem; }
.sb-melody-file { font-size: 0.7rem; color: var(--text-dim); flex: 1; min-width: 0; }
.sb-melody-file::file-selector-button {
  background: var(--surface); border: 1px solid var(--surface-hover); border-radius: 5px;
  color: var(--accent); font-size: 0.7rem; padding: 0.25rem 0.6rem; cursor: pointer;
  margin-right: 0.5rem;
}
.sb-melody-clear {
  width: 24px; height: 24px; flex-shrink: 0; padding: 0;
  background: var(--surface); border: 1px solid var(--surface-hover); border-radius: 4px;
  color: var(--text-dim); font-size: 0.7rem; cursor: pointer; line-height: 1;
}
.sb-melody-clear:hover { color: var(--error); }
</style>
