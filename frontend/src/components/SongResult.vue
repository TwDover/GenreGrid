<!--
  GenreGrid — a style-based MIDI generator.
  Copyright (C) 2026 Tw Dover

  This program is free software: you can redistribute it and/or modify it under
  the terms of the GNU General Public License v3 or (at your option) any later
  version. Distributed WITHOUT ANY WARRANTY. See <https://www.gnu.org/licenses/>.
-->
<template>
  <div class="song-result">
    <div v-if="!result" class="sr-empty">
      <span class="sr-empty-icon">♫</span>
      <span>Build a full song to see its timeline and draggable parts.</span>
      <button class="btn btn-primary" @click="emit('open-setup')">Open Setup</button>
    </div>

    <template v-else>
      <!-- Header + whole-song actions -->
      <div class="sr-header">
        <button class="btn-primary sr-play-btn" :class="{ playing: isPlaying }" @click="togglePlay">
          <span class="sr-play-glyph">{{ isPlaying ? '■' : '▶' }}</span>
          <span>{{ isPlaying ? 'Stop' : 'Play' }}</span>
        </button>
        <div class="sr-title-block">
          <span class="sr-title">{{ label }}</span>
          <span class="sr-meta">{{ styleName }} · {{ result.total_bars }} bars · {{ result.bpm }} BPM · {{ result.key }}</span>
        </div>
        <div class="sr-actions">
          <button class="sr-dl-btn" @click="download">↓ .mid</button>
          <button class="sr-dl-btn" :disabled="renderingWav" @click="exportSongWav" :title="wavError || 'Render and download the full song as WAV — see the ⬇ header button for progress from anywhere'">
            <span v-if="renderingWav">{{ Math.round(wavProgress * 100) }}%</span>
            <span v-else>↓ .wav</span>
          </button>
          <div class="sr-history">
            <button class="sr-dl-btn" @click="toggleHistory" title="Restore an earlier version of this song">⟲ History</button>
            <div v-if="historyOpen" class="sr-history-menu">
              <div v-if="!songVersions.length" class="sr-history-empty">No earlier versions yet — re-rolls create them</div>
              <button
                v-for="v in songVersions"
                :key="v.id"
                class="sr-history-item"
                :disabled="restoreLoading !== null"
                @click="onRestore(v.id)"
              >{{ restoreLoading === v.id ? 'Restoring…' : v.saved_at.replace('T', ' ') }}</button>
            </div>
          </div>
        </div>
      </div>

      <!-- Section timeline — click a block to play from there, ⟳ to re-roll it -->
      <div class="sr-timeline">
        <div
          v-for="(sec, i) in result.sections"
          :key="sec.name"
          class="sr-tl-block"
          :class="[`seg-${sec.section_type}`, { 'sr-tl-busy': sectionRegenLoading === i, 'sr-tl-playing': playingSectionIndex === i }]"
          :style="{ flex: sec.bars }"
          :title="`${sec.name} · ${sec.bars} bars${sec.quality != null ? ` · quality ${(sec.quality * 100).toFixed(0)}%` : ''} — click to play from here`"
          @click="seekToSection(sec)"
        >
          <span
            v-if="sec.quality != null"
            class="sr-tl-dot"
            :class="sec.quality >= 0.82 ? 'q-good' : sec.quality >= 0.7 ? 'q-ok' : 'q-weak'"
          />
          <span class="sr-tl-name">{{ sec.name }}</span>
          <button
            v-if="sec.section_type !== 'ending'"
            class="sr-tl-regen"
            :disabled="sectionRegenLoading !== null"
            :title="`Re-roll ${sec.name}`"
            @click.stop="onRegenSection(i)"
          >{{ sectionRegenLoading === i ? '…' : '⟳' }}</button>
        </div>
        <div v-if="playheadPct !== null" class="sr-playhead" :style="{ left: `${playheadPct}%` }" />
      </div>

      <!-- Progression strip: roman numerals + concrete chords per bar, pinned
           across section re-rolls. Doubles as a theory-learning surface. -->
      <div v-if="progressionChips.length" class="sr-prog">
        <div class="sr-prog-head">
          <span class="sr-prog-title">Progression</span>
          <span class="sr-prog-lock" title="Pinned — every section and re-roll uses this progression">🔒 locked</span>
          <button v-if="!editingProg" class="sr-prog-edit" @click="startEditProg" title="Edit the progression and rebuild the song">✎ edit</button>
        </div>

        <!-- Read-only view: roman + concrete chord + cadence/color labels -->
        <div v-if="!editingProg" class="sr-prog-strip">
          <div
            v-for="(c, i) in progressionChips"
            :key="i"
            class="sr-prog-chip"
            :class="{ 'sr-prog-cadence': c.cadence, 'sr-prog-color': c.color }"
            :title="c.title"
          >
            <span class="sr-prog-roman">{{ c.roman }}</span>
            <span class="sr-prog-chord">{{ c.chord }}</span>
            <span v-if="c.cadence" class="sr-prog-cad-label">{{ c.cadence }}</span>
          </div>
        </div>

        <!-- Edit mode: one roman input per bar (datalist-suggested), then rebuild -->
        <div v-else class="sr-prog-editor">
          <div class="sr-prog-inputs">
            <div v-for="(_, i) in editProg" :key="i" class="sr-prog-input-cell">
              <input
                class="sr-prog-input"
                :class="{ invalid: !isValidRoman(editProg[i]) }"
                v-model="editProg[i]"
                list="sr-prog-suggest"
                :placeholder="`bar ${i + 1}`"
                @keyup.enter="applyProg"
              />
              <span class="sr-prog-input-chord">{{ editChord(i) }}</span>
            </div>
            <button class="sr-prog-len" title="Add a bar" @click="editProg.push('I')">＋</button>
            <button v-if="editProg.length > 2" class="sr-prog-len" title="Remove last bar" @click="editProg.pop()">－</button>
          </div>
          <datalist id="sr-prog-suggest">
            <option v-for="s in ROMAN_SUGGESTIONS" :key="s" :value="s" />
          </datalist>
          <div v-if="progError" class="sr-prog-err">{{ progError }}</div>
          <div class="sr-prog-editor-actions">
            <button class="sr-prog-apply" :disabled="progBusy || !editValid" @click="applyProg">
              {{ progBusy ? 'Rebuilding…' : 'Apply & rebuild' }}
            </button>
            <button class="sr-prog-cancel" :disabled="progBusy" @click="editingProg = false">Cancel</button>
          </div>
        </div>
      </div>

      <!-- Draggable per-part stems -->
      <div class="sr-parts-label">Parts <span class="sr-hint">🔒 lock to keep a part through section re-rolls · ⟳ re-roll · drag ⠿ into your DAW</span></div>
      <div v-if="regenError" class="sr-error">{{ regenError }}</div>
      <div class="sr-stems">
        <template v-for="file in bustedStems" :key="file.part">
          <PartCard
            :file="file"
            :styleId="result.style"
            :keyRoot="keyRoot"
            :scale="scale"
            :regenLoading="regenLoading === file.part"
            :hasUndo="undoable.has(file.part)"
            :simple="true"
            :lockable="true"
            :rollable="true"
            :locked="locked.has(file.part)"
            :editable="true"
            :gain="partGains[file.part] ?? 1.0"
            @regen="onRegen"
            @roll="onRoll"
            @toggle-lock="onToggleLock"
            @edited="onEdited"
            @undo="onUndo(file.part)"
            @gain="onGain"
          />
          <CandidatePicker
            v-if="candidatePart === file.part && candidates.length"
            :candidates="candidates"
            :part="file.part"
            :styleId="result.style"
            :keyRoot="keyRoot"
            :scale="scale"
            :keeping="keepingIndex"
            @keep="onKeepCandidate"
            @cancel="closeCandidates"
          />
        </template>
      </div>

      <!-- Parts not in this build — one click generates and adds the stem -->
      <div v-if="missingParts.length" class="sr-add-row">
        <span class="sr-add-label">Add a part</span>
        <button
          v-for="p in missingParts"
          :key="p"
          class="sr-add-btn"
          :disabled="addLoading !== null"
          :title="`Generate ${p} for this song`"
          @click="onAdd(p)"
        >
          <span v-if="addLoading === p">…</span>
          <span v-else>＋ {{ p.replace('_', ' ') }}</span>
        </button>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onUnmounted } from 'vue'
import type { BuildSongResponse, FileInfo } from '../types/midi'
import { downloadUrl, regenerateSongPart, regenerateSongSection, undoSongPart, listSongVersions, restoreSongVersion, setPartGain, rollSongPartCandidates, keepSongPartCandidate, rebuildSongProgression, type SongVersion, type SongPartCandidate } from '../services/api'
import { resolveProgression } from '../utils/chordResolver'
import CandidatePicker from './CandidatePicker.vue'
import { useMidiPlayer } from '../composables/useMidiPlayer'
import { useToasts } from '../composables/useToasts'
import { logError } from '../composables/useErrorLog'
import { useDownloadPrompt } from '../composables/useDownloadPrompt'
import { useRenderQueue } from '../composables/useRenderQueue'
import { useStyleCatalog } from '../composables/useStyleCatalog'
import PartCard from './PartCard.vue'

const props = defineProps<{ result: BuildSongResponse | null; label: string }>()
const emit = defineEmits<{
  (e: 'rebuilt', result: BuildSongResponse, label: string): void
  (e: 'open-setup'): void
}>()

const { toggle, stop: stopPlayer, currentlyPlaying, seek, positionSeconds, offlineRender, cue } = useMidiPlayer()
const { toast } = useToasts()
const { promptFilename } = useDownloadPrompt()
const { startJob, updateProgress, completeJob, failJob } = useRenderQueue()
let songBlobUrl: string | null = null
const renderingWav = ref(false)
const wavProgress = ref(0)
const wavError = ref('')

// Cache-bust versions per part (and the song) after a regeneration.
const versions = reactive<Record<string, number>>({})
const regenLoading = ref<string | null>(null)
const regenError = ref<string | null>(null)
const undoable = reactive(new Set<string>())

// Part locks: locked stems are held byte-identical through a section re-roll
// (the backend restores them). Hand-edited parts auto-lock so an accidental
// section re-roll can't discard the user's note edits. Reset on a new song.
const locked = reactive(new Set<string>())
watch(() => props.result?.generation_id, () => locked.clear())
function onToggleLock(part: string) {
  locked.has(part) ? locked.delete(part) : locked.add(part)
}
function onEdited(part: string) {
  locked.add(part)
  toast(`${part.replace('_', ' ')} locked — edits protected from section re-rolls`)
}

// ── Compare-and-keep (roll ×N candidates) ────────────────────────────────────
const candidatePart = ref<string | null>(null)
const candidates = ref<SongPartCandidate[]>([])
const keepingIndex = ref<number | null>(null)
watch(() => props.result?.generation_id, () => closeCandidates())

function closeCandidates() {
  candidatePart.value = null
  candidates.value = []
  keepingIndex.value = null
}

async function onRoll(part: string) {
  if (!props.result || regenLoading.value) return
  regenLoading.value = part
  regenError.value = null
  closeCandidates()
  try {
    const list = await rollSongPartCandidates({ generation_id: props.result.generation_id, part, count: 3 })
    candidatePart.value = part
    candidates.value = list.map(c => ({ ...c, url: `${c.url}?v=${Date.now()}` }))
  } catch (e: any) {
    regenError.value = e.message ?? 'Rolling candidates failed'
    logError('Roll song part candidates', e)
    toast(regenError.value ?? 'Rolling candidates failed', 'error')
  } finally {
    regenLoading.value = null
  }
}

async function onKeepCandidate(index: number) {
  if (!props.result || !candidatePart.value || keepingIndex.value !== null) return
  const part = candidatePart.value
  keepingIndex.value = index
  regenError.value = null
  try {
    await keepSongPartCandidate({ generation_id: props.result.generation_id, part, index })
    const v = Date.now()
    versions[part] = v
    versions.song = v
    undoable.add(part)
    closeCandidates()
    toast(`Kept ${part.replace('_', ' ')} variation ${index + 1}`)
  } catch (e: any) {
    regenError.value = e.message ?? 'Keeping candidate failed'
    logError('Keep song part candidate', e)
    toast(regenError.value ?? 'Keeping candidate failed', 'error')
    keepingIndex.value = null
  }
}

// Every part the song builder can produce — parts absent from the build are
// offered as one-click "add" buttons under the stems.
const ALL_PARTS = ['chords', 'bass', 'melody', 'drums', 'arpeggio', 'pads', 'counter_melody']
// Stems generated after the build via "add a part" (the result prop is immutable)
const addedFiles = ref<FileInfo[]>([])
const addLoading = ref<string | null>(null)
watch(() => props.result?.generation_id, () => { addedFiles.value = [] })

const stemFiles = computed(() => [
  ...(props.result?.files ?? []).filter(f => f.part !== 'song'),
  ...addedFiles.value,
])
const missingParts = computed(() => {
  if (!props.result) return []
  const have = new Set(stemFiles.value.map(f => f.part))
  return ALL_PARTS.filter(p => !have.has(p))
})
const bustedStems = computed(() => stemFiles.value.map(f =>
  versions[f.part] ? { ...f, url: `${f.url}?v=${versions[f.part]}` } : f))
const keyRoot = computed(() => (props.result?.key ?? 'C').split(' ')[0])
const scale = computed(() => (props.result?.key ?? 'C minor').split(' ')[1] ?? 'minor')

// Pretty style name from the shared catalog; fall back to de-slugging the id
// (e.g. "dark_trap" → "Dark Trap") when the catalog hasn't loaded.
const { catalog } = useStyleCatalog()
const styleName = computed(() => {
  const id = props.result?.style
  if (!id) return ''
  const known = catalog.value.get(id)?.name
  if (known) return known
  return id.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
})

// ── Progression strip ────────────────────────────────────────────────────────
// Roman numerals → concrete chords, with cadence labels at phrase ends and a
// flag on chromatic-color chords (secondary dominants / borrowed chords).
// Expected (non-exotic) romans per mode — anything else reads as chromatic color
// (a secondary dominant or a borrowed chord). V is included in minor since the
// raised dominant is idiomatic, not exotic.
const DIATONIC_MINOR = new Set(['i', 'ii', 'iidim', 'iio', 'III', 'iv', 'v', 'V', 'VI', 'VII'])
const DIATONIC_MAJOR = new Set(['I', 'ii', 'iii', 'IV', 'V', 'vi', 'viidim', 'viio'])
// Strip chord-quality suffixes to the bare roman (V7 → V, iim7b5 → ii).
const baseRoman = (r: string) => r.replace(/(maj7|m7b5|dim7|sus[24]|add\d+|maj|dim|aug|\d+)/gi, '')
function cadenceLabel(roman: string, next: string | null): string {
  const nextIsTonic = /^(I|i)(?![IVX])/.test(next ?? '')
  if (/^V(?![IVX])/i.test(roman)) return nextIsTonic ? 'authentic' : 'half'
  if (/^(iv|IV)(?![IVX])/.test(roman) && nextIsTonic) return 'plagal'
  return ''
}
const progressionChips = computed(() => {
  const prog = props.result?.progression
  if (!prog || !prog.length) return []
  const chords = resolveProgression(prog, keyRoot.value, scale.value)
  const diatonic = scale.value.startsWith('major') ? DIATONIC_MAJOR : DIATONIC_MINOR
  return prog.map((roman, i) => {
    const phraseEnd = i % 4 === 3 || i === prog.length - 1
    const cadence = phraseEnd ? cadenceLabel(roman, prog[i + 1] ?? null) : ''
    const color = !diatonic.has(baseRoman(roman))
    return {
      roman,
      chord: chords[i],
      cadence,
      color,
      title: `Bar ${i + 1}: ${roman} = ${chords[i]}${cadence ? ` · ${cadence} cadence` : ''}${color ? ' · chromatic color chord' : ''}`,
    }
  })
})

// ── Progression editing ──────────────────────────────────────────────────────
const ROMAN_SUGGESTIONS = [
  'I', 'ii', 'iii', 'IV', 'V', 'vi', 'viidim',        // major diatonic
  'i', 'iidim', 'III', 'iv', 'v', 'VI', 'VII',        // minor diatonic
  'II', 'VII', 'bVI', 'bVII', 'bII', 'bIII',          // secondary dominants / borrowed
  'V7', 'IV7', 'i7', 'IVmaj7', 'iim7b5',              // sevenths
]
const ROMAN_RE = /^[b#]?(VII|VI|IV|V|III|II|I|vii|vi|iv|v|iii|ii|i)(maj7|m7b5|dim7|dim|aug|sus[24]|add\d+|m?6|m?7|m?9|\+)?$/
const isValidRoman = (r: string) => ROMAN_RE.test((r ?? '').trim())

const editingProg = ref(false)
const editProg = ref<string[]>([])
const progBusy = ref(false)
const progError = ref('')
watch(() => props.result?.generation_id, () => { editingProg.value = false })

const editValid = computed(() =>
  editProg.value.length >= 2 && editProg.value.every(r => isValidRoman(r)))

function startEditProg() {
  editProg.value = [...(props.result?.progression ?? [])]
  progError.value = ''
  editingProg.value = true
}
function editChord(i: number): string {
  const r = editProg.value[i]
  if (!isValidRoman(r)) return '—'
  return resolveProgression([r.trim()], keyRoot.value, scale.value)[0]
}
async function applyProg() {
  if (!props.result || progBusy.value || !editValid.value) return
  progBusy.value = true
  progError.value = ''
  try {
    const result = await rebuildSongProgression({
      generation_id: props.result.generation_id,
      progression: editProg.value.map(r => r.trim()),
    })
    editingProg.value = false
    emit('rebuilt', result, `${props.label} (edited harmony)`)
    toast('Song rebuilt with your progression')
  } catch (e: any) {
    progError.value = e.message ?? 'Rebuild failed'
    logError('Rebuild song progression', e)
  } finally {
    progBusy.value = false
  }
}

const songFile = computed(() => props.result?.files.find(f => f.part === 'song') ?? null)
const songUrl = computed(() => {
  if (!songFile.value) return null
  return versions.song ? `${songFile.value.url}?v=${versions.song}` : songFile.value.url
})
const isPlaying = computed(() => songBlobUrl !== null && currentlyPlaying.value === songBlobUrl)

// ── Live playhead ────────────────────────────────────────────────────────────
// Playback position in bars, mirroring the piecewise tempo map used by
// seekToSection (choruses run 1.2% faster than the base tempo).
const playheadBar = computed<number | null>(() => {
  if (!props.result || !isPlaying.value) return null
  const bpm = props.result.bpm || 120
  let remaining = positionSeconds.value
  let bars = 0
  for (const s of props.result.sections) {
    const isChorus = s.section_type === 'chorus' || s.section_type === 'post_chorus'
    const secDur = s.bars * 4 * 60 / (isChorus ? bpm * 1.012 : bpm)
    if (remaining < secDur) return bars + (remaining / secDur) * s.bars
    remaining -= secDur
    bars += s.bars
  }
  return bars
})
const playheadPct = computed<number | null>(() => {
  if (playheadBar.value === null || !props.result?.total_bars) return null
  return Math.min(100, (playheadBar.value / props.result.total_bars) * 100)
})
const playingSectionIndex = computed(() => {
  if (playheadBar.value === null || !props.result) return -1
  let acc = 0
  for (let i = 0; i < props.result.sections.length; i++) {
    acc += props.result.sections[i].bars
    if (playheadBar.value < acc) return i
  }
  return -1
})

async function onRegen(part: string) {
  if (!props.result || regenLoading.value) return
  regenLoading.value = part
  regenError.value = null
  try {
    await regenerateSongPart({ generation_id: props.result.generation_id, part })
    const v = Date.now()
    versions[part] = v      // reload the stem card + piano roll
    versions.song = v       // and the whole-song playback
    undoable.add(part)
    toast(`Re-rolled ${part.replace('_', ' ')}`)
  } catch (e: any) {
    regenError.value = e.message ?? 'Regeneration failed'
    logError('Regenerate part', e)
    toast(regenError.value ?? 'Regeneration failed', 'error')
  } finally {
    regenLoading.value = null
  }
}

// ── Mixer ────────────────────────────────────────────────────────────────────
// Per-part gains (1.0 = generated balance), seeded from the song's persisted
// mixer state and updated optimistically as sliders move.
const partGains = reactive<Record<string, number>>({})
watch(() => props.result, (r) => {
  for (const k of Object.keys(partGains)) delete partGains[k]
  if (r?.mixer) Object.assign(partGains, r.mixer)
}, { immediate: true })

async function onGain(part: string, gain: number) {
  if (!props.result) return
  const prev = partGains[part] ?? 1.0
  partGains[part] = gain
  regenError.value = null
  try {
    await setPartGain({ generation_id: props.result.generation_id, part, gain })
    const v = Date.now()
    versions[part] = v
    versions.song = v
    toast(`${part.replace('_', ' ')} volume applied`)
  } catch (e: any) {
    partGains[part] = prev
    regenError.value = e.message ?? 'Volume change failed'
    logError('Set part gain', e)
    toast(regenError.value ?? 'Volume change failed', 'error')
  }
}

// ── Version history ──────────────────────────────────────────────────────────
const historyOpen = ref(false)
const songVersions = ref<SongVersion[]>([])
const restoreLoading = ref<string | null>(null)
watch(() => props.result?.generation_id, () => { historyOpen.value = false; songVersions.value = [] })

async function toggleHistory() {
  historyOpen.value = !historyOpen.value
  if (historyOpen.value && props.result) {
    songVersions.value = await listSongVersions(props.result.generation_id)
  }
}

async function onRestore(versionId: string) {
  if (!props.result || restoreLoading.value) return
  restoreLoading.value = versionId
  regenError.value = null
  try {
    const files = await restoreSongVersion({ generation_id: props.result.generation_id, version_id: versionId })
    const v = Date.now()
    for (const f of files) versions[f.part] = v
    versions.song = v
    // A restore may add back stems that were later removed, or drop added ones —
    // reflect the restored file set in the "added" list so the cards match disk.
    const restored = new Set(files.map(f => f.part))
    addedFiles.value = addedFiles.value.filter(f => restored.has(f.part))
    historyOpen.value = false
    songVersions.value = await listSongVersions(props.result.generation_id)
    toast('Version restored')
  } catch (e: any) {
    regenError.value = e.message ?? 'Restore failed'
    logError('Restore song version', e)
    toast(regenError.value ?? 'Restore failed', 'error')
  } finally {
    restoreLoading.value = null
  }
}

const sectionRegenLoading = ref<number | null>(null)

async function onRegenSection(index: number) {
  if (!props.result || sectionRegenLoading.value !== null) return
  sectionRegenLoading.value = index
  regenError.value = null
  try {
    const files = await regenerateSongSection({
      generation_id: props.result.generation_id, section_index: index,
      locked_parts: [...locked],
    })
    // Only the returned (unlocked) stems changed — bust those; locked stems are
    // held byte-identical by the backend and must not be reloaded.
    const v = Date.now()
    for (const f of files) versions[f.part] = v
    versions.song = v
    for (const f of files) if (f.part !== 'song') undoable.add(f.part)
    const lockNote = locked.size ? ` (kept ${[...locked].join(', ')})` : ''
    toast(`Re-rolled ${props.result.sections[index]?.name ?? 'section'}${lockNote}`)
  } catch (e: any) {
    regenError.value = e.message ?? 'Section regeneration failed'
    logError('Regenerate song section', e)
    toast(regenError.value ?? 'Section regeneration failed', 'error')
  } finally {
    sectionRegenLoading.value = null
  }
}

async function seekToSection(sec: { start_bar: number }) {
  if (!props.result) return
  // Piecewise beat→seconds mirroring the backend tempo map: choruses run 1.2%
  // faster than the base tempo, so a flat conversion drifts on long songs.
  const bpm = props.result.bpm || 120
  let seconds = 0
  for (const s of props.result.sections) {
    if (s.start_bar >= sec.start_bar) break
    const isChorus = s.section_type === 'chorus' || s.section_type === 'post_chorus'
    seconds += s.bars * 4 * 60 / (isChorus ? bpm * 1.012 : bpm)
  }
  if (!isPlaying.value) await togglePlay()
  seek(seconds)
}

async function onAdd(part: string) {
  if (!props.result || addLoading.value) return
  addLoading.value = part
  regenError.value = null
  try {
    const fi = await regenerateSongPart({ generation_id: props.result.generation_id, part })
    addedFiles.value = [...addedFiles.value, fi]
    const v = Date.now()
    versions[part] = v
    versions.song = v   // song.mid was rebuilt with the new stem
    toast(`Added ${part.replace('_', ' ')}`)
  } catch (e: any) {
    regenError.value = e.message ?? `Could not add ${part}`
    logError('Add song part', e)
    toast(regenError.value ?? `Could not add ${part}`, 'error')
  } finally {
    addLoading.value = null
  }
}

async function onUndo(part: string) {
  if (!props.result) return
  regenError.value = null
  try {
    await undoSongPart({ generation_id: props.result.generation_id, part })
    const v = Date.now()
    versions[part] = v
    versions.song = v
    undoable.delete(part)   // one level of undo
  } catch (e: any) {
    regenError.value = e.message ?? 'Undo failed'
    logError('Undo song part', e)
  }
}

// Hand the docked transport this song, so its ▶ starts playback from down
// there too — the header button and the transport are the same action.
watch(() => props.result?.generation_id, () => {
  if (props.result) cue(props.label || 'Song', togglePlay)
  else cue(null, null)
}, { immediate: true })
watch(() => props.label, l => { if (props.result) cue(l || 'Song', togglePlay) })
onUnmounted(() => cue(null, null))

async function togglePlay() {
  if (isPlaying.value) { stopPlayer(); return }
  if (!songUrl.value) return
  try {
    const res = await fetch(downloadUrl(songUrl.value))
    const blob = await res.blob()
    if (songBlobUrl) URL.revokeObjectURL(songBlobUrl)
    songBlobUrl = URL.createObjectURL(blob)
    await toggle(songBlobUrl, props.result?.style, props.label)
  } catch { /* playback failure is non-fatal */ }
}

async function download() {
  if (!songFile.value || !props.result) return
  const defaultName = `${props.result.style}_song_${props.result.generation_id.slice(0, 8)}`
  const name = await promptFilename(defaultName, 'mid', 'Save song')
  if (name === null) return   // cancelled
  const a = document.createElement('a')
  a.href = downloadUrl(songFile.value.url)
  a.download = `${name}.mid`
  a.click()
}

async function exportSongWav() {
  if (!songFile.value || !props.result || renderingWav.value) return
  const defaultName = `${props.result.style}_song_${props.result.generation_id.slice(0, 8)}`
  const name = await promptFilename(defaultName, 'wav', 'Export song as WAV')
  if (name === null) return   // cancelled
  renderingWav.value = true
  wavProgress.value = 0
  wavError.value = ''
  // Tracked in the shared render queue too — switching to another mode tab
  // unmounts this whole component, but the render keeps going regardless, and
  // the queue is what stays visible to show it finished (or failed).
  const jobId = startJob(`Song — ${defaultName}`, `${name}.wav`)
  try {
    // Nominal bar duration, padded: the chorus tempo push and closing
    // ritardando make the real playback slightly longer than a flat bpm
    // calculation, and offlineRender's buffer must cover the whole thing.
    const duration = (props.result.total_bars * 4 * 60 / props.result.bpm) * 1.05 + 2
    const blob = await offlineRender(songFile.value.url, props.result.style, duration, 'all', v => {
      wavProgress.value = v
      updateProgress(jobId, v)
    })
    completeJob(jobId, blob)
    toast('Song exported as WAV')
  } catch (e: any) {
    wavError.value = e?.message ?? 'WAV export failed'
    failJob(jobId, wavError.value)
    logError('Song WAV export', e)
    toast(wavError.value, 'error')
  } finally {
    renderingWav.value = false
  }
}
</script>

<style scoped>
.song-result { display: flex; flex-direction: column; gap: 0.75rem; }

.sr-empty {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: var(--s4); padding: var(--s7) var(--s4); text-align: center;
  max-width: 30rem; margin: var(--s6) auto 0;
  color: var(--ink-faint); font-size: var(--t-body); line-height: 1.6;
}
.sr-empty-icon { font-size: 2rem; color: var(--ink-faint); }

/* Sticky so the song's identity and its play button stay on screen while you
 * scroll through the stems below. */
.sr-header {
  display: flex; align-items: center; gap: var(--s4);
  position: sticky; top: 0; z-index: 10;
  background: linear-gradient(var(--ground) 80%, transparent);
  padding: var(--s5) 0 var(--s4);
}
.sr-title-block { display: flex; flex-direction: column; gap: 2px; min-width: 0; flex: 1; }
.sr-title { font-size: var(--t-display); font-weight: 640; letter-spacing: -.02em; color: var(--ink); }
.sr-meta { font-size: var(--t-meta); font-family: var(--f-mono); font-variant-numeric: tabular-nums; color: var(--ink-dim); }

.sr-actions { display: flex; gap: 0.5rem; flex-shrink: 0; }

/* The song-level play button. Deliberately the largest control in the
 * workspace — every other ▶ on the page is a per-stem preview. */
.sr-play-btn {
  font-size: 0.85rem;
  padding: 0.55rem 1.1rem;
  flex-shrink: 0;
}
.sr-play-glyph { font-size: 0.75rem; }
.sr-dl-btn {
  font-size: 0.75rem; padding: 0.35rem 0.65rem; background: var(--panel-deep);
  border: 1px solid var(--surface); border-radius: 5px; color: var(--text-dim); cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.sr-dl-btn:hover { background: var(--surface); color: var(--text); }

/* Version history dropdown */
.sr-history { position: relative; }
.sr-history-menu {
  position: absolute; right: 0; top: calc(100% + 4px); z-index: 20;
  background: var(--panel); border: 1px solid var(--surface); border-radius: 6px;
  min-width: 190px; padding: 0.25rem; display: flex; flex-direction: column; gap: 2px;
  box-shadow: 0 6px 18px rgba(0,0,0,0.5);
}
.sr-history-empty { font-size: 0.65rem; color: var(--text-faint); padding: 0.35rem 0.5rem; }
.sr-history-item {
  font-size: 0.7rem; font-family: monospace; text-align: left;
  background: transparent; border: none; border-radius: 4px;
  color: var(--text-dim); cursor: pointer; padding: 0.3rem 0.5rem;
}
.sr-history-item:hover:not(:disabled) { background: var(--surface); color: var(--accent); }
.sr-history-item:disabled { opacity: 0.5; cursor: wait; }

/* Timeline — the arrangement is the workspace hero, not a sliver. */
.sr-timeline { position: relative; display: flex; height: 72px; border-radius: var(--r-md); overflow: hidden; gap: 2px; background: var(--sunken); }
.sr-playhead {
  position: absolute; top: 0; bottom: 0; width: 2px;
  background: var(--accent); box-shadow: 0 0 6px color-mix(in srgb, var(--accent) 60%, transparent);
  pointer-events: none; z-index: 2;
}
.sr-tl-block {
  display: flex; align-items: flex-start; justify-content: space-between;
  padding: var(--s2) var(--s3); overflow: hidden; min-width: 0; gap: 0.2rem;
  transition: filter 0.15s;
  cursor: pointer;
}
.sr-tl-block:hover { filter: brightness(1.07) saturate(1.08); }
.sr-tl-block.sr-tl-busy { filter: brightness(0.7); cursor: wait; }
.sr-tl-block.sr-tl-playing { filter: brightness(1.3); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--accent) 53%, transparent); }
.sr-tl-name { font-size: var(--t-meta); font-weight: 600; color: var(--seg-text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; letter-spacing: -.005em; }
.sr-tl-dot { width: 5px; height: 5px; border-radius: 50%; flex-shrink: 0; }
.q-good { background: var(--success); }
.q-ok   { background: var(--gold); }
.q-weak { background: var(--error); }
.sr-tl-regen {
  background: none; border: none; padding: 0; flex-shrink: 0;
  font-size: 0.6rem; line-height: 1; color: var(--seg-text-faint); cursor: pointer;
  opacity: 0; transition: opacity 0.15s, color 0.15s;
}
.sr-tl-block:hover .sr-tl-regen { opacity: 1; }
.sr-tl-regen:hover:not(:disabled) { color: var(--seg-text); }
.sr-tl-regen:disabled { cursor: wait; }

/* Progression strip */
.sr-prog { display: flex; flex-direction: column; gap: 0.3rem; }
.sr-prog-head { display: flex; align-items: baseline; gap: 0.5rem; }
.sr-prog-title { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-dim); }
.sr-prog-lock { font-size: 0.62rem; color: var(--text-faint); }
.sr-prog-strip { display: flex; gap: 3px; overflow-x: auto; padding-bottom: 2px; }
.sr-prog-chip {
  position: relative; flex: 1 0 auto; min-width: 46px;
  display: flex; flex-direction: column; align-items: center; gap: 1px;
  padding: 0.3rem 0.4rem 0.5rem; border-radius: 5px;
  background: var(--panel-deep); border: 1px solid var(--surface);
}
.sr-prog-chip.sr-prog-color { border-color: color-mix(in srgb, var(--gold) 45%, transparent); background: color-mix(in srgb, var(--gold) 8%, var(--panel-deep)); }
.sr-prog-chip.sr-prog-cadence { border-right-width: 2px; border-right-color: color-mix(in srgb, var(--accent) 45%, transparent); }
.sr-prog-roman { font-size: 0.72rem; font-weight: 700; color: var(--accent); font-family: monospace; }
.sr-prog-chord { font-size: 0.6rem; color: var(--text-dim); }
.sr-prog-cad-label {
  position: absolute; bottom: 1px; font-size: 0.48rem; letter-spacing: 0.02em;
  color: var(--text-faint); text-transform: uppercase;
}
.sr-prog-edit {
  margin-left: auto; font-size: 0.62rem; background: transparent; border: none;
  color: var(--text-dim); cursor: pointer;
}
.sr-prog-edit:hover { color: var(--accent); }

/* Progression editor */
.sr-prog-editor { display: flex; flex-direction: column; gap: 0.4rem; }
.sr-prog-inputs { display: flex; flex-wrap: wrap; gap: 4px; align-items: stretch; }
.sr-prog-input-cell { display: flex; flex-direction: column; align-items: center; gap: 1px; }
.sr-prog-input {
  width: 52px; text-align: center; font-family: monospace; font-size: 0.72rem; font-weight: 700;
  color: var(--accent); background: var(--panel-deep); border: 1px solid var(--surface);
  border-radius: 5px; padding: 0.3rem 0.2rem;
}
.sr-prog-input:focus { outline: none; border-color: var(--accent); }
.sr-prog-input.invalid { border-color: var(--error); color: var(--error); }
.sr-prog-input-chord { font-size: 0.58rem; color: var(--text-dim); }
.sr-prog-len {
  width: 26px; font-size: 0.9rem; line-height: 1; color: var(--text-dim);
  background: var(--panel-deep); border: 1px dashed var(--surface); border-radius: 5px; cursor: pointer;
}
.sr-prog-len:hover { color: var(--accent); border-color: color-mix(in srgb, var(--accent) 40%, transparent); }
.sr-prog-err { font-size: 0.68rem; color: var(--error); }
.sr-prog-editor-actions { display: flex; gap: 0.4rem; }
.sr-prog-apply {
  font-size: 0.72rem; padding: 0.35rem 0.8rem; border-radius: 5px; cursor: pointer;
  background: var(--accent-surface-strong); border: 1px solid color-mix(in srgb, var(--accent) 45%, transparent);
  color: var(--accent);
}
.sr-prog-apply:hover:not(:disabled) { background: var(--accent-surface); }
.sr-prog-apply:disabled { opacity: 0.5; cursor: not-allowed; }
.sr-prog-cancel {
  font-size: 0.72rem; padding: 0.35rem 0.7rem; border-radius: 5px; cursor: pointer;
  background: var(--panel-deep); border: 1px solid var(--surface); color: var(--text-dim);
}
.sr-prog-cancel:hover:not(:disabled) { background: var(--surface); color: var(--text); }
.sr-prog-cancel:disabled { opacity: 0.5; }

.sr-parts-label {
  font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-dim);
  display: flex; align-items: baseline; gap: 0.5rem;
}
.sr-hint { font-size: 0.65rem; text-transform: none; letter-spacing: 0; color: var(--text-faint); }

.sr-stems { display: flex; flex-direction: column; border-top: 1px solid var(--line); }

.sr-error { font-size: 0.72rem; color: var(--error); background: var(--error-surface); border-radius: 4px; padding: 0.3rem 0.5rem; }

/* "Add a part" ghost row */
.sr-add-row { display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap; }
.sr-add-label {
  font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-faint);
  flex-shrink: 0;
}
.sr-add-btn {
  font-size: 0.7rem; padding: 0.3rem 0.6rem;
  background: transparent; border: 1px dashed var(--surface); border-radius: 6px;
  color: var(--text-dim); cursor: pointer; transition: border-color 0.15s, color 0.15s;
}
.sr-add-btn:hover:not(:disabled) { border-color: color-mix(in srgb, var(--accent) 40%, transparent); color: var(--accent); }
.sr-add-btn:disabled { opacity: 0.5; cursor: wait; }

/* Section type colors */
.seg-intro { background: var(--seg-intro); }
.seg-verse { background: var(--seg-verse); }
.seg-pre_chorus { background: var(--seg-pre_chorus); }
.seg-chorus { background: var(--seg-chorus); }
.seg-post_chorus { background: var(--seg-post_chorus); }
.seg-bridge { background: var(--seg-bridge); }
.seg-instrumental_solo { background: var(--seg-instrumental_solo); }
.seg-outro { background: var(--seg-outro); }
.seg-ending { background: var(--seg-ending); }
</style>
