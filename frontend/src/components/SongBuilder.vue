<template>
  <div class="song-builder">
    <!-- Header -->
    <div class="sb-header">
      <span class="sb-title">Song Builder</span>
      <span class="sb-hint">Generate a full song in one click</span>
    </div>

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
        <label class="sb-label">BPM</label>
        <input type="number" v-model.number="form.bpm" min="40" max="240" class="sb-input" />
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

    <!-- Generate Button -->
    <button class="sb-generate-btn" :disabled="loading || form.parts.length === 0" @click="generate">
      <span v-if="loading" class="sb-spinner">●</span>
      <span v-if="loading">Building song…</span>
      <span v-else>▶ Build Full Song</span>
    </button>
    <div v-if="error" class="sb-error">{{ error }}</div>

    <!-- Result -->
    <template v-if="result">
      <div class="sb-result-header">
        <span class="sb-result-title">{{ templateLabel }} — {{ result.total_bars }} bars · {{ result.bpm }} BPM</span>
        <span class="sb-result-key">{{ result.key }}</span>
      </div>

      <!-- Section timeline -->
      <div class="sb-timeline">
        <div
          v-for="sec in result.sections"
          :key="sec.name"
          class="sb-tl-block"
          :class="`seg-${sec.section_type}`"
          :style="{ flex: sec.bars }"
          :title="`${sec.name} · ${sec.bars} bars`"
        >
          <span class="sb-tl-name">{{ sec.name }}</span>
          <span class="sb-tl-bars">{{ sec.bars }}b</span>
        </div>
      </div>

      <!-- Section list -->
      <div class="sb-sections">
        <div v-for="sec in result.sections" :key="sec.name" class="sb-sec-row">
          <span class="sb-sec-dot" :class="`seg-${sec.section_type}`" />
          <span class="sb-sec-name">{{ sec.name }}</span>
          <span class="sb-sec-meta">{{ sec.bars }} bars · bar {{ sec.start_bar + 1 }} · {{ sec.key }}</span>
        </div>
      </div>

      <!-- Actions -->
      <div class="sb-actions">
        <button class="sb-play-btn" :class="{ playing: isPlaying }" @click="togglePlay">
          {{ isPlaying ? '■ Stop' : '▶ Play' }}
        </button>
        <button class="sb-dl-btn" @click="download">↓ Download MIDI</button>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { StyleInfo, BuildSongResponse } from '../types/midi'
import { buildSong, downloadUrl } from '../services/api'
import { useMidiPlayer } from '../composables/useMidiPlayer'

const props = defineProps<{ styles: StyleInfo[] }>()

const { toggle, stop: stopPlayer, currentlyPlaying } = useMidiPlayer()

const keys = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
const allParts = ['chords', 'bass', 'melody', 'drums', 'arpeggio']

interface TemplateSection { name: string; bars: number; type: string }
interface TemplateOption { id: string; label: string; totalBars: number; sections: TemplateSection[] }

const templates: TemplateOption[] = [
  {
    id: 'verse_chorus',
    label: 'Verse–Chorus',
    totalBars: 56,
    sections: [
      { name: 'Intro',    bars: 4,  type: 'intro'  },
      { name: 'Verse',    bars: 16, type: 'verse'  },
      { name: 'Chorus',   bars: 8,  type: 'chorus' },
      { name: 'Verse 2',  bars: 16, type: 'verse'  },
      { name: 'Chorus 2', bars: 8,  type: 'chorus' },
      { name: 'Outro',    bars: 4,  type: 'outro'  },
    ],
  },
  {
    id: 'verse_chorus_bridge',
    label: 'V–C–Bridge',
    totalBars: 80,
    sections: [
      { name: 'Intro',        bars: 4,  type: 'intro'      },
      { name: 'Verse',        bars: 16, type: 'verse'      },
      { name: 'Pre-Chorus',   bars: 4,  type: 'pre_chorus' },
      { name: 'Chorus',       bars: 8,  type: 'chorus'     },
      { name: 'Verse 2',      bars: 16, type: 'verse'      },
      { name: 'Pre-Chorus 2', bars: 4,  type: 'pre_chorus' },
      { name: 'Chorus 2',     bars: 8,  type: 'chorus'     },
      { name: 'Bridge',       bars: 8,  type: 'bridge'     },
      { name: 'Final Chorus', bars: 8,  type: 'chorus'     },
      { name: 'Outro',        bars: 4,  type: 'outro'      },
    ],
  },
  {
    id: 'extended',
    label: 'Extended',
    totalBars: 80,
    sections: [
      { name: 'Intro',        bars: 4,  type: 'intro'             },
      { name: 'Verse',        bars: 16, type: 'verse'             },
      { name: 'Chorus',       bars: 8,  type: 'chorus'            },
      { name: 'Verse 2',      bars: 16, type: 'verse'             },
      { name: 'Chorus 2',     bars: 8,  type: 'chorus'            },
      { name: 'Instrumental', bars: 8,  type: 'instrumental_solo' },
      { name: 'Bridge',       bars: 8,  type: 'bridge'            },
      { name: 'Final Chorus', bars: 8,  type: 'chorus'            },
      { name: 'Outro',        bars: 4,  type: 'outro'             },
    ],
  },
  {
    id: 'compact',
    label: 'Compact',
    totalBars: 40,
    sections: [
      { name: 'Intro',    bars: 4, type: 'intro'  },
      { name: 'Verse',    bars: 8, type: 'verse'  },
      { name: 'Chorus',   bars: 8, type: 'chorus' },
      { name: 'Verse 2',  bars: 8, type: 'verse'  },
      { name: 'Chorus 2', bars: 8, type: 'chorus' },
      { name: 'Outro',    bars: 4, type: 'outro'  },
    ],
  },
  {
    id: 'minimal',
    label: 'Minimal',
    totalBars: 24,
    sections: [
      { name: 'Intro', bars: 4,  type: 'intro' },
      { name: 'Main',  bars: 16, type: 'verse' },
      { name: 'Outro', bars: 4,  type: 'outro' },
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
  parts: ['chords', 'bass', 'melody', 'drums'],
  template: 'verse_chorus',
})

const loading = ref(false)
const error = ref<string | null>(null)
const result = ref<BuildSongResponse | null>(null)
let songBlobUrl: string | null = null

const templateLabel = computed(
  () => templates.find(t => t.id === form.value.template)?.label ?? form.value.template
)

const songFileUrl = computed(() => {
  if (!result.value) return null
  const f = result.value.files.find(f => f.part === 'song')
  return f ? downloadUrl(f.url) : null
})

const isPlaying = computed(
  () => songBlobUrl !== null && currentlyPlaying.value === songBlobUrl
)

async function generate() {
  loading.value = true
  error.value = null
  result.value = null
  if (songBlobUrl) { URL.revokeObjectURL(songBlobUrl); songBlobUrl = null }
  try {
    result.value = await buildSong({ ...form.value })
  } catch (e: any) {
    error.value = e.message ?? 'Song generation failed'
  } finally {
    loading.value = false
  }
}

async function togglePlay() {
  if (isPlaying.value) { stopPlayer(); return }
  const url = songFileUrl.value
  if (!url) return
  try {
    const res = await fetch(url)
    const blob = await res.blob()
    if (songBlobUrl) URL.revokeObjectURL(songBlobUrl)
    songBlobUrl = URL.createObjectURL(blob)
    await toggle(songBlobUrl, form.value.style_id, templateLabel.value)
  } catch (e: any) {
    error.value = e.message ?? 'Playback failed'
  }
}

function download() {
  const url = songFileUrl.value
  if (!url) return
  const a = document.createElement('a')
  a.href = url
  a.download = `song_${result.value?.generation_id ?? 'export'}.mid`
  a.click()
}
</script>

<style scoped>
.song-builder {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding: 0.75rem;
  background: #060f14;
  border: 1px solid #0d2535;
  border-radius: 10px;
}

.sb-header {
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
}
.sb-title {
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #4a7080;
  font-weight: 600;
}
.sb-hint {
  font-size: 0.68rem;
  color: #2a4550;
}

.sb-section { display: flex; flex-direction: column; gap: 0.35rem; }
.sb-label { font-size: 0.68rem; color: #4a7080; font-weight: 500; display: flex; align-items: center; gap: 0.4rem; }
.sb-val { color: #00c8ff; font-family: monospace; }

/* Template cards */
.template-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 0.35rem;
}
.tpl-card {
  background: #040a0e;
  border: 1px solid #0d2535;
  border-radius: 6px;
  padding: 0.4rem 0.5rem 0.35rem;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  text-align: left;
  transition: border-color 0.15s, background 0.15s;
}
.tpl-card:hover { border-color: #1a4060; background: #061218; }
.tpl-card.active { border-color: #00c8ff66; background: #001e35; }
.tpl-name { font-size: 0.7rem; font-weight: 600; color: #c0c8d0; }
.tpl-bars { font-size: 0.6rem; font-family: monospace; color: #2a4550; }
.tpl-strip {
  display: flex;
  height: 6px;
  border-radius: 3px;
  overflow: hidden;
  gap: 1px;
}
.tpl-seg { min-width: 2px; border-radius: 1px; }

/* Row / field layout */
.sb-row { display: flex; gap: 0.6rem; align-items: flex-end; }
.sb-field { display: flex; flex-direction: column; gap: 0.2rem; flex: 1; }
.sb-field-sm { flex: 0 0 auto; min-width: 72px; }

.sb-select, .sb-input {
  background: #040a0e;
  border: 1px solid #0d2535;
  border-radius: 5px;
  color: #c0c8d0;
  font-size: 0.75rem;
  padding: 0.28rem 0.45rem;
  width: 100%;
  box-sizing: border-box;
}
.sb-select:focus, .sb-input:focus { outline: none; border-color: #00c8ff44; }

.sb-range { width: 100%; accent-color: #00c8ff; cursor: pointer; }

/* Parts toggles */
.sb-parts { display: flex; flex-wrap: wrap; gap: 0.35rem; }
.sb-part-toggle {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.72rem;
  color: #4a7080;
  cursor: pointer;
}
.sb-part-toggle input { accent-color: #00c8ff; cursor: pointer; }
.sb-part-toggle:hover span { color: #c0c8d0; }

/* Generate button */
.sb-generate-btn {
  padding: 0.55rem 1rem;
  background: #001e35;
  border: 1px solid #00c8ff55;
  border-radius: 7px;
  color: #00c8ff;
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.4rem;
  transition: background 0.15s, border-color 0.15s;
}
.sb-generate-btn:hover:not(:disabled) { background: #003450; border-color: #00c8ff; }
.sb-generate-btn:disabled { opacity: 0.5; cursor: default; }

.sb-spinner {
  animation: spin 1s linear infinite;
  display: inline-block;
}
@keyframes spin { to { transform: rotate(360deg); } }

.sb-error {
  font-size: 0.72rem;
  color: #f87171;
  background: #2a1010;
  border-radius: 4px;
  padding: 0.3rem 0.5rem;
}

/* Result */
.sb-result-header {
  display: flex;
  align-items: baseline;
  gap: 0.6rem;
  padding-top: 0.25rem;
  border-top: 1px solid #0d2535;
}
.sb-result-title { font-size: 0.78rem; font-weight: 600; color: #c0c8d0; }
.sb-result-key { font-size: 0.68rem; font-family: monospace; color: #4a7080; }

/* Timeline */
.sb-timeline {
  display: flex;
  height: 28px;
  border-radius: 5px;
  overflow: hidden;
  gap: 1px;
  background: #020608;
}
.sb-tl-block {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 0.3rem;
  overflow: hidden;
  min-width: 0;
  gap: 0.2rem;
  transition: filter 0.15s;
}
.sb-tl-block:hover { filter: brightness(1.2); }
.sb-tl-name { font-size: 0.58rem; color: rgba(255,255,255,0.55); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; }
.sb-tl-bars { font-size: 0.52rem; font-family: monospace; color: rgba(255,255,255,0.3); flex-shrink: 0; }

/* Section list */
.sb-sections {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  max-height: 160px;
  overflow-y: auto;
}
.sb-sec-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.2rem 0.4rem;
  border-radius: 4px;
}
.sb-sec-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.sb-sec-name { font-size: 0.72rem; font-weight: 500; color: #c0c8d0; min-width: 90px; }
.sb-sec-meta { font-size: 0.65rem; color: #4a7080; font-family: monospace; }

/* Actions */
.sb-actions { display: flex; gap: 0.5rem; }
.sb-play-btn {
  font-size: 0.75rem;
  padding: 0.3rem 0.75rem;
  background: #001e35;
  border: 1px solid #00c8ff44;
  border-radius: 5px;
  color: #00c8ff;
  cursor: pointer;
  transition: background 0.15s;
}
.sb-play-btn:hover { background: #003450; }
.sb-play-btn.playing { background: #003450; border-color: #00c8ff; }
.sb-dl-btn {
  font-size: 0.75rem;
  padding: 0.3rem 0.65rem;
  background: #040a0e;
  border: 1px solid #0d2535;
  border-radius: 5px;
  color: #4a7080;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.sb-dl-btn:hover { background: #0d2535; color: #e0e0e8; }

/* Section type color coding */
.seg-intro,          .sb-sec-dot.seg-intro          { background: #1a4060; }
.seg-verse,          .sb-sec-dot.seg-verse          { background: #1a5040; }
.seg-pre_chorus,     .sb-sec-dot.seg-pre_chorus     { background: #3a4a20; }
.seg-chorus,         .sb-sec-dot.seg-chorus         { background: #005580; }
.seg-post_chorus,    .sb-sec-dot.seg-post_chorus    { background: #204060; }
.seg-bridge,         .sb-sec-dot.seg-bridge         { background: #502060; }
.seg-instrumental_solo, .sb-sec-dot.seg-instrumental_solo { background: #603020; }
.seg-outro,          .sb-sec-dot.seg-outro          { background: #102030; }
</style>
