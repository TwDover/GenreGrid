<!--
  GenreGrid — a style-based MIDI generator.
  Copyright (C) 2026 Tw Dover

  This program is free software: you can redistribute it and/or modify it under
  the terms of the GNU General Public License v3 or (at your option) any later
  version. Distributed WITHOUT ANY WARRANTY. See <https://www.gnu.org/licenses/>.
-->
<template>
  <div class="song-form setup-form">
    <!-- Template picker — full width above the groups -->
    <div class="tpl-section">
      <span class="eyebrow">Template</span>
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
          <select v-model="sec.section_type" class="ce-type">
            <option v-for="t in SECTION_TYPES" :key="t" :value="t">{{ t.replace('_', ' ') }}</option>
          </select>
          <input v-model.number="sec.bars" type="number" min="1" max="32" class="ce-bars" />
          <select v-model="sec.style_id" class="ce-style" title="Optional per-section style">
            <option value="">song style</option>
            <option v-for="s in styles" :key="s.id" :value="s.id">{{ s.name }}</option>
          </select>
          <button class="btn ce-btn" :disabled="i === 0" @click="moveSection(i, -1)" title="Move up">↑</button>
          <button class="btn ce-btn" :disabled="i === customSections.length - 1" @click="moveSection(i, 1)" title="Move down">↓</button>
          <button class="btn ce-btn ce-del" :disabled="customSections.length <= 1" @click="customSections.splice(i, 1)" title="Remove">✕</button>
        </div>
        <button class="btn ce-add" :disabled="customSections.length >= 20" @click="customSections.push({ section_type: 'verse', bars: 8, style_id: '' })">＋ section</button>
      </div>
    </div>

    <div class="setup-grid">
      <!-- ── Sound ──────────────────────────────────────────────────────── -->
      <section class="group">
        <span class="eyebrow">Sound</span>
        <div class="field">
          <label>Style</label>
          <select v-model="form.style_id">
            <option v-for="s in styles" :key="s.id" :value="s.id">{{ s.name }}</option>
          </select>
        </div>
        <div class="field-row">
          <div class="field">
            <label>Key</label>
            <select v-model="form.key">
              <option v-for="k in keys" :key="k" :value="k">{{ k }}</option>
            </select>
          </div>
          <div class="field">
            <label>Scale</label>
            <select v-model="form.scale">
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
        </div>
        <p v-if="scaleMood" class="scale-mood">{{ scaleMood }}</p>
        <div class="field">
          <label>BPM <span v-if="selectedStyle" class="hint">{{ selectedStyle.bpm_range[0] }}–{{ selectedStyle.bpm_range[1] }}</span></label>
          <input type="number" v-model.number="form.bpm"
                 :min="selectedStyle?.bpm_range[0] ?? 40"
                 :max="selectedStyle?.bpm_range[1] ?? 240" />
        </div>
      </section>

      <!-- ── Form ───────────────────────────────────────────────────────── -->
      <section class="group">
        <span class="eyebrow">Form</span>
        <div class="field">
          <label>Parts</label>
          <div class="part-toggles">
            <label v-for="p in allParts" :key="p" class="toggle">
              <input type="checkbox" :value="p" v-model="form.parts" />
              {{ p.replace('_', ' ') }}
            </label>
          </div>
        </div>
      </section>

      <!-- ── Feel ───────────────────────────────────────────────────────── -->
      <section class="group">
        <span class="eyebrow">Feel</span>
        <div class="field">
          <label>Complexity <span class="value">{{ form.complexity.toFixed(2) }}</span></label>
          <input type="range" v-model.number="form.complexity" min="0" max="1" step="0.01" />
        </div>
        <div class="field">
          <label>Variation <span class="value">{{ form.variation.toFixed(2) }}</span></label>
          <input type="range" v-model.number="form.variation" min="0" max="1" step="0.01" />
        </div>
        <div class="field">
          <label>Dynamics <span class="value">{{ form.dynamics.toFixed(2) }}</span></label>
          <input type="range" v-model.number="form.dynamics" min="0" max="1" step="0.01"
                 title="How hard the arrangement dramatizes: drops, fills, breakdowns, verse/chorus contrast. 0 = steady beat-tape, 1 = every lift pushed." />
        </div>
      </section>
    </div>

    <!-- ── Advanced ─────────────────────────────────────────────────────── -->
    <details class="advanced">
      <summary>Advanced — key lifts, blending, your own MIDI</summary>
      <div class="adv-grid">
        <section class="group">
          <div class="field">
            <label>Chorus key shift <span class="hint">lift choruses</span></label>
            <select v-model.number="form.chorus_key_shift">
              <option :value="0">none</option>
              <option :value="1">+1 (½ step)</option>
              <option :value="2">+2 (whole)</option>
              <option :value="3">+3</option>
              <option :value="5">+5 (4th)</option>
              <option :value="-2">−2</option>
              <option :value="-5">−5</option>
            </select>
          </div>
          <div class="field">
            <label>Final chorus lift <span class="hint">the classic gear change</span></label>
            <select v-model.number="form.final_chorus_lift">
              <option :value="0">none</option>
              <option :value="1">+1</option>
              <option :value="2">+2</option>
            </select>
          </div>
        </section>

        <section class="group">
          <div class="field">
            <label>Blend with <span class="hint">optional second style</span></label>
            <select v-model="form.blend_style_id">
              <option value="">none</option>
              <option v-for="s in styles.filter(s => s.id !== form.style_id)" :key="s.id" :value="s.id">{{ s.name }}</option>
            </select>
          </div>
          <div class="field" v-if="form.blend_style_id">
            <label>Blend amount <span class="value">{{ form.blend_amount.toFixed(2) }}</span></label>
            <input type="range" v-model.number="form.blend_amount" min="0" max="1" step="0.05" />
          </div>
          <label class="prior-toggle" v-if="selectedStyle?.has_prior">
            <input type="checkbox" v-model="form.use_priors" />
            <span>Use my local MIDI corpus <span class="hint">overlays patterns mined from a corpus you provide; you're responsible for its license</span></span>
          </label>
        </section>

        <section class="group">
          <div class="field">
            <label>Build around my melody <span class="hint">becomes the song's hook, key auto-detected</span></label>
            <div class="melody-row">
              <input ref="melodyInput" type="file" accept=".mid,.midi" class="melody-file" @change="onMelodyFile" />
              <button v-if="melodyFile" class="btn btn-icon melody-clear" @click="clearMelodyFile" title="Remove file">✕</button>
            </div>
          </div>
        </section>
      </div>
    </details>

    <!-- Build button. No ▶ here: that glyph means playback everywhere else. -->
    <div class="sb-actions">
      <button class="btn-primary sb-generate-btn" :disabled="loading || form.parts.length === 0" @click="generate">
        <span v-if="loading" class="sb-spinner">●</span>
        <span v-if="loading">Building song…</span>
        <span v-else-if="melodyFile">Build Song Around My Melody</span>
        <span v-else>Build Full Song</span>
      </button>
      <div v-if="error" class="sb-error">{{ error }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { StyleInfo, BuildSongRequest, BuildSongResponse } from '../types/midi'
import { errorMessage } from '../utils/errors'
import { buildSong, buildSongFromMelody } from '../services/api'
import { logError } from '../composables/useErrorLog'

const props = defineProps<{ styles: StyleInfo[] }>()
const emit = defineEmits<{
  (e: 'built', result: BuildSongResponse, label: string): void
  (e: 'building', v: boolean): void
}>()

const keys = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
const allParts = ['chords', 'bass', 'melody', 'drums', 'arpeggio', 'pads', 'counter_melody']

// One-line "sounds like" for each scale, so choosing one doesn't require theory.
const SCALE_MOODS: Record<string, string> = {
  major:            'Bright, happy, resolved — the default “pop” sound.',
  minor:            'Dark, serious, emotional — the default for most modern genres.',
  dorian:           'Minor but hopeful — jazzy, funky, a touch brighter than minor.',
  phrygian:         'Tense and exotic — that flat-2nd Spanish/metal edge.',
  mixolydian:       'Bluesy and relaxed — major with a dominant, rock/funk feel.',
  pentatonic_minor: 'Safe and bluesy — five notes that rarely clash. Great for solos.',
  pentatonic_major: 'Open and cheerful — easy, folk/country brightness.',
  blues:            'Gritty and soulful — pentatonic minor plus the “blue” note.',
  harmonic_minor:   'Dramatic and classical — that exotic raised-7th cadence.',
}

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
  dynamics: 0.5,
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
const scaleMood = computed(() => SCALE_MOODS[form.value.scale] ?? '')
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
    const payload: BuildSongRequest = { ...form.value }
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
  } catch (e) {
    error.value = errorMessage(e) ?? 'Song generation failed'
    logError('Build song', e)
  } finally {
    loading.value = false
    emit('building', false)
  }
}
</script>

<style scoped>
.song-form { display: flex; flex-direction: column; gap: var(--s5); }

.tpl-section { display: flex; flex-direction: column; gap: var(--s3); }

/* Template cards — auto-fill so they wrap cleanly at any drawer width. */
.template-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: var(--s2); }
.tpl-card {
  background: var(--ground); border: 1px solid var(--line); border-radius: var(--r-md);
  padding: var(--s2) var(--s3) var(--s3); cursor: pointer; display: flex;
  flex-direction: column; gap: var(--s2); text-align: left;
  transition: border-color 0.14s, background 0.14s;
}
.tpl-card:hover { border-color: var(--ink-faint); }
.tpl-card.active { border-color: var(--accent); background: var(--accent-wash); }
.tpl-name { font-size: var(--t-meta); font-weight: 600; color: var(--ink); }
.tpl-bars { font-size: var(--t-micro); font-family: var(--f-mono); color: var(--ink-faint); }
.tpl-strip { display: flex; height: 6px; border-radius: 3px; overflow: hidden; gap: 1px; }
.tpl-seg { min-width: 2px; border-radius: 1px; }

.sb-spinner { animation: spin 1s linear infinite; display: inline-block; }
@keyframes spin { to { transform: rotate(360deg); } }

.scale-mood { margin: 0; font-size: var(--t-meta); color: var(--ink-faint); line-height: 1.4; }

.prior-toggle {
  display: flex; align-items: flex-start; gap: var(--s2);
  cursor: pointer; font-size: var(--t-meta); color: var(--ink-dim);
}
.prior-toggle input { width: auto; margin: 3px 0 0; accent-color: var(--accent); }

/* Build button — sticks to the bottom of the drawer so it stays reachable. */
.sb-actions {
  position: sticky;
  bottom: 0;
  z-index: 3;
  display: flex;
  flex-direction: column;
  gap: var(--s2);
  margin-top: var(--s3);
  /* Owns the drawer's bottom spacing so the fill pins flush to the scroll-area
   * bottom — nothing shows through beneath the Build button while scrolling. */
  padding: var(--s3) 0 var(--s5);
  background: var(--raised);
  box-shadow: 0 -10px 14px -2px var(--raised);
}
.sb-generate-btn { height: 42px; font-size: var(--t-body); }
.sb-error { font-size: var(--t-meta); color: var(--bad); background: var(--error-surface); border-radius: var(--r-sm); padding: 0.3rem 0.5rem; }

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
.custom-editor { display: flex; flex-direction: column; gap: var(--s2); margin-top: var(--s2); }
.ce-row { display: flex; align-items: center; gap: var(--s2); }
.ce-type { flex: 1; min-width: 0; }
.ce-bars { width: 64px; flex-shrink: 0; }
.ce-style { flex: 1; min-width: 0; }
.ce-btn { width: 30px; padding: 0; flex-shrink: 0; }
.ce-del:hover:not(:disabled) { color: var(--bad); border-color: var(--bad); }
.ce-add { border-style: dashed; align-self: flex-start; color: var(--ink-dim); }
.ce-add:hover:not(:disabled) { color: var(--accent); border-color: var(--accent-edge); }

/* Melody import */
.melody-row { display: flex; align-items: center; gap: var(--s2); }
.melody-file { font-size: var(--t-meta); color: var(--ink-dim); flex: 1; min-width: 0; height: auto; padding: 0; border: none; background: transparent; }
.melody-file::file-selector-button {
  font: inherit; font-size: var(--t-meta);
  background: var(--raised); border: 1px solid var(--line); border-radius: var(--r-sm);
  color: var(--accent); padding: 0.3rem 0.6rem; cursor: pointer; margin-right: 0.5rem;
}
.melody-clear:hover { color: var(--bad); border-color: var(--bad); }
</style>
