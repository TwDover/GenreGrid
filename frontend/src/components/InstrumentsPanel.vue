<!--
  GenreGrid — a style-based MIDI generator.
  Copyright (C) 2026 Tw Dover

  This program is free software: you can redistribute it and/or modify it under
  the terms of the GNU General Public License as published by the Free Software
  Foundation, either version 3 of the License, or (at your option) any later
  version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
  <https://www.gnu.org/licenses/> for details.
-->
<template>
  <div v-if="panelOpen" class="ip-overlay" @click.self="close" @keydown.esc="close">
    <div class="ip-modal" role="dialog" aria-label="Custom instruments">
      <header class="ip-header">
        <h2>Instruments</h2>
        <button class="ip-x" title="Close" @click="close">✕</button>
      </header>

      <p v-if="!supported()" class="ip-note">
        Custom instruments need the GenreGrid desktop app — this feature is unavailable in the browser build.
      </p>

      <template v-else>
        <!-- ── Lineup: what this style plays, and what you can swap in ───────── -->
        <section class="ip-lineup">
          <div class="ip-lineup-head">
            <h3>Lineup</h3>
            <select v-model="styleId" class="ip-input ip-style">
              <option v-for="s in styleOptions" :key="s.id" :value="s.id">{{ s.name }}</option>
            </select>
          </div>

          <p v-if="!styleOptions.length" class="ip-empty">No styles loaded yet.</p>
          <template v-else>
            <div class="ip-scope">
              <span class="ip-scope-label">Changes apply to</span>
              <label><input v-model="scope" type="radio" value="style" /> This style only</label>
              <label><input v-model="scope" type="radio" value="all" /> All styles</label>
            </div>

            <div v-for="row in lineup" :key="row.part" class="ip-row">
              <span class="ip-part">{{ row.partLabel }}</span>
              <span class="ip-builtin" :title="row.builtin">{{ row.builtin }}</span>
              <select
                class="ip-input ip-pick"
                :value="currentAssignment(row.part) ?? ''"
                @change="onAssign(row.part, ($event.target as HTMLSelectElement).value)"
              >
                <option value="">Built-in</option>
                <option v-for="inst in instrumentsFor(row.part)" :key="inst.id" :value="inst.id">
                  {{ inst.name }}
                </option>
              </select>
              <button
                v-if="row.part === 'drums' && assignedKit"
                class="ip-mini"
                title="Edit kit pieces"
                @click="editKitId = assignedKit.id"
              >
                ✎ pieces
              </button>
              <span v-else class="ip-mini-spacer"></span>
            </div>
            <p v-if="scope === 'style' && inheritedNote" class="ip-hint ip-inherit">{{ inheritedNote }}</p>
          </template>
        </section>

        <!-- ── Kit editor ───────────────────────────────────────────────────── -->
        <section v-if="editKit" class="ip-kit">
          <div class="ip-lineup-head">
            <h3>Kit pieces — {{ editKit.name }}</h3>
            <button class="ip-mini" @click="editKitId = null">Done</button>
          </div>
          <p class="ip-hint">
            Empty pieces play the synthesized kit, so a partial kit works straight away.
          </p>
          <div v-for="slot in DRUM_SLOTS" :key="slot.pitch" class="ip-slot">
            <span class="ip-slot-name">{{ slot.label }}</span>
            <select
              class="ip-input ip-slot-pick"
              :value="slotFile(slot.pitch)"
              @change="onSlot(slot.pitch, ($event.target as HTMLSelectElement).value)"
            >
              <option value="">— empty (synth) —</option>
              <option v-for="f in kitFileChoices" :key="f" :value="f">{{ f }}</option>
            </select>
            <button
              class="ip-audition"
              :title="slotFile(slot.pitch) ? 'Hear this sample' : 'Hear the synth fallback'"
              @click="audition(slot.pitch)"
            >▶</button>
          </div>
          <p v-if="!kitFileChoices.length" class="ip-empty">
            This instrument has no stored audio files.
          </p>
        </section>

        <!-- ── Library ──────────────────────────────────────────────────────── -->
        <section class="ip-lib">
          <h3>Your instruments ({{ instruments.length }})</h3>
          <p v-if="!instruments.length" class="ip-empty">None yet — add one below.</p>
          <ul v-else class="ip-list">
            <li v-for="inst in instruments" :key="inst.id" class="ip-item">
              <span class="ip-name">{{ inst.name }}</span>
              <span class="ip-meta">{{ kindLabel(inst) }}</span>
              <button v-if="inst.kind === 'drums'" class="ip-mini" @click="editKitId = inst.id">✎ pieces</button>
              <button class="ip-del" title="Delete" @click="remove(inst)">Delete</button>
            </li>
          </ul>
        </section>

        <!-- ── Add ──────────────────────────────────────────────────────────── -->
        <section class="ip-add">
          <h3>Add an instrument</h3>
          <p class="ip-hint">
            <strong>Melodic / Bass:</strong> drop one sound (pitched across the keyboard), or files
            named by note (<code>C4.wav</code>, <code>A#3.mp3</code>). Sub-folders like
            <code>soft/</code>, <code>hard/</code> become velocity layers.<br />
            <strong>Drums:</strong> drop a kit folder — files are matched to pieces by name
            (<code>kick.wav</code>, <code>hh_closed.wav</code>); anything unrecognised you place yourself.
          </p>
          <p class="ip-hint">
            Need sounds? Free, redistributable one-shots: <strong>Freesound</strong> (filter to the
            CC0 licence), <strong>99Sounds</strong>, or MusicRadar’s <strong>SampleRadar</strong>.
            Whatever you import stays on your machine — it’s never bundled with GenreGrid — so you
            only need the right to use it yourself.
          </p>
          <div class="ip-add-row">
            <input v-model="newName" class="ip-input" type="text" placeholder="Instrument name" />
            <select v-model="newKind" class="ip-input ip-kind">
              <option value="melodic">Melodic</option>
              <option value="bass">Bass</option>
              <option value="drums">Drum kit</option>
            </select>
          </div>
          <div class="ip-add-row">
            <label class="ip-file">
              Choose files
              <input ref="filesInput" type="file" accept="audio/*,.mp3,.wav,.ogg,.flac,.m4a" multiple @change="onPick" />
            </label>
            <label class="ip-file">
              Choose folder
              <input ref="folderInput" type="file" webkitdirectory @change="onPick" />
            </label>
            <span v-if="pickedCount" class="ip-picked">{{ pickedCount }} file(s) selected</span>
          </div>
          <div class="ip-add-row">
            <button class="ip-btn" :disabled="!canImport || importing" @click="doImport">
              {{ importing ? 'Importing…' : 'Add instrument' }}
            </button>
            <span v-if="error" class="ip-err">{{ error }}</span>
            <span v-if="notice" class="ip-picked">{{ notice }}</span>
          </div>
        </section>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue'
import { useCustomInstruments } from '../composables/useCustomInstruments'
import { useStyleCatalog, instrumentLabel } from '../composables/useStyleCatalog'
import { drumCharacterForStyle } from '../soundfonts/drums'
import { auditionPiece, auditionSynthPiece, disposeAudition } from '../soundfonts/audition'
import type { PlayerPart } from '../composables/useMidiPlayer'
import { DRUM_SLOTS, type CustomInstrument } from '../soundfonts/customInstruments'

const {
  instruments, assignments, panelOpen, supported,
  ensureLoaded, importInstrument, deleteInstrument, assignPart,
  getInstrument, materializeKit, updateKitSlot, storedFileNames,
} = useCustomInstruments()
const { catalog, activeStyleId } = useStyleCatalog()

// ── Lineup ───────────────────────────────────────────────────────────────────
// Ordered as you'd read a mixer, not as PLAYER_PARTS happens to be declared.
const LINEUP_PARTS: PlayerPart[] = ['drums', 'bass', 'chords', 'melody', 'arpeggio', 'pads', 'counter_melody']

const styleId = ref<string>('')
const scope = ref<'style' | 'all'>('all')

const styleOptions = computed(() =>
  [...catalog.value.values()].map(s => ({ id: s.id, name: s.name })).sort((a, b) => a.name.localeCompare(b.name)),
)

watch(panelOpen, (open) => {
  if (!open) {
    disposeAudition()   // free the preview synth kits when the panel closes
    return
  }
  ensureLoaded()
  // Open on what's playing; fall back to the first style so the panel is never blank.
  styleId.value = activeStyleId.value ?? styleOptions.value[0]?.id ?? ''
  editKitId.value = null
})

onUnmounted(disposeAudition)

function partLabel(p: PlayerPart): string {
  return p === 'counter_melody' ? 'Counter-melody' : p.charAt(0).toUpperCase() + p.slice(1)
}

// What the style plays on each part today. Drums aren't in the instrument registry
// (they're a synthesized kit chosen by style character), so they get their own label.
const lineup = computed(() =>
  LINEUP_PARTS.map(part => ({
    part,
    partLabel: partLabel(part),
    builtin: part === 'drums'
      ? `${drumCharacterForStyle(styleId.value)} kit`
      : (instrumentLabel(styleId.value, part) ?? '—'),
  })).filter(row => row.builtin !== '—'),
)

/** Only offer instruments that make sense on a part: a kit on drums, a pitched
 *  instrument anywhere else. This is what `kind` is for. */
function instrumentsFor(part: PlayerPart): CustomInstrument[] {
  return instruments.value.filter(i => (part === 'drums' ? i.kind === 'drums' : i.kind !== 'drums'))
}

function currentAssignment(part: PlayerPart): string | undefined {
  if (scope.value !== 'style') return assignments.value.defaults[part]
  const perStyle = assignments.value.perStyle?.[styleId.value]?.[part]
  // An entry of '' is a deliberate "built-in here"; only a MISSING entry inherits.
  return perStyle !== undefined ? perStyle : assignments.value.defaults[part]
}

function onAssign(part: PlayerPart, id: string) {
  assignPart(part, id || null, scope.value === 'style' ? styleId.value : undefined)
}

// When a style-scoped view is showing a value that actually comes from the global
// default, say so — otherwise "This style only" looks like it already has overrides.
const inheritedNote = computed(() => {
  const overrides = assignments.value.perStyle?.[styleId.value] ?? {}
  const inherited = LINEUP_PARTS.filter(p => overrides[p] === undefined && assignments.value.defaults[p])
  return inherited.length
    ? `${inherited.map(partLabel).join(', ')} shown from the all-styles default until you change them here.`
    : ''
})

// ── Kit editor ───────────────────────────────────────────────────────────────
const editKitId = ref<string | null>(null)
const editKit = computed(() => (editKitId.value ? getInstrument(editKitId.value) ?? null : null))
const kitFileChoices = ref<string[]>([])

// The kit currently assigned to drums, so the lineup row can offer "edit pieces".
const assignedKit = computed(() => {
  const id = currentAssignment('drums')
  const inst = id ? getInstrument(id) : undefined
  return inst?.kind === 'drums' ? inst : null
})

watch(editKitId, async (id) => {
  kitFileChoices.value = id ? await storedFileNames(id) : []
})

function slotFile(pitch: number): string {
  const layers = editKit.value?.kit?.[pitch]?.layers
  const first = layers?.[0] && Object.values(layers[0].urls)[0]
  return Array.isArray(first) ? first[0] : (first ?? '')
}

async function onSlot(pitch: number, file: string) {
  if (!editKitId.value) return
  await updateKitSlot(editKitId.value, pitch, file ? [file] : [])
}

/** Play one kit piece so a mis-mapped file is caught here, not on playback: the
 *  user's sample if the slot is filled, else the synth fallback it would use. */
async function audition(pitch: number) {
  if (!editKitId.value) return
  if (slotFile(pitch)) {
    const kit = await materializeKit(editKitId.value)
    const manifest = kit?.[pitch]
    if (manifest?.layers.length) await auditionPiece(manifest)
  } else {
    await auditionSynthPiece(pitch, styleId.value || undefined)
  }
}

// ── Library / import ─────────────────────────────────────────────────────────
const newName = ref('')
const newKind = ref<CustomInstrument['kind']>('melodic')
const picked = ref<File[]>([])
const filesInput = ref<HTMLInputElement | null>(null)
const folderInput = ref<HTMLInputElement | null>(null)
const importing = ref(false)
const error = ref('')
const notice = ref('')

const pickedCount = computed(() => picked.value.length)
const canImport = computed(() => picked.value.length > 0 && newName.value.trim().length > 0)

function kindLabel(inst: CustomInstrument): string {
  if (inst.kind === 'drums') {
    return `drum kit · ${Object.keys(inst.kit ?? {}).length} piece(s)`
  }
  return `${inst.kind} · ${inst.manifest.layers.length} layer(s)`
}

function onPick(e: Event) {
  const input = e.target as HTMLInputElement
  picked.value = input.files ? Array.from(input.files) : []
  error.value = ''
  notice.value = ''
}

async function doImport() {
  if (!canImport.value) return
  importing.value = true
  error.value = ''
  notice.value = ''
  try {
    const result = await importInstrument(newName.value, newKind.value, picked.value)
    if (!result) { error.value = 'No usable audio files found.'; return }
    notice.value = result.unmatched.length
      ? `Added. ${result.unmatched.length} file(s) matched no piece — place them under “pieces”.`
      : 'Added.'
    if (result.instrument.kind === 'drums' && result.unmatched.length) {
      editKitId.value = result.instrument.id
    }
    newName.value = ''
    picked.value = []
    if (filesInput.value) filesInput.value.value = ''
    if (folderInput.value) folderInput.value.value = ''
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Import failed.'
  } finally {
    importing.value = false
  }
}

async function remove(inst: CustomInstrument) {
  if (!confirm(`Delete “${inst.name}”?`)) return
  await deleteInstrument(inst.id)
  if (editKitId.value === inst.id) editKitId.value = null
}

function close() { panelOpen.value = false }
</script>

<style scoped>
.ip-overlay {
  position: fixed; inset: 0; z-index: 1000;
  background: rgba(0, 0, 0, 0.5);
  display: flex; align-items: center; justify-content: center; padding: 1rem;
}
.ip-modal {
  background: var(--surface); color: var(--text);
  border: 1px solid var(--border); border-radius: 10px;
  width: min(620px, 100%); max-height: 86vh; overflow: auto;
  padding: 1rem 1.25rem;
}
.ip-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.5rem; }
.ip-header h2 { margin: 0; font-size: 1.1rem; }
.ip-x { background: none; border: none; color: var(--text-faint); cursor: pointer; font-size: 1rem; }
.ip-x:hover { color: var(--text); }
.ip-note { color: var(--text-faint); }
section { border-top: 1px solid var(--border); padding-top: 0.85rem; margin-top: 0.85rem; }
h3 { font-size: 0.85rem; margin: 0 0 0.4rem; color: var(--text); }
.ip-hint { font-size: 0.78rem; color: var(--text-faint); margin: 0 0 0.6rem; line-height: 1.5; }
.ip-hint code { background: var(--surface-muted); padding: 0 0.25rem; border-radius: 3px; }
.ip-inherit { margin: 0.5rem 0 0; font-style: italic; }
.ip-input {
  font: inherit; padding: 0.35rem 0.5rem; border: 1px solid var(--border);
  border-radius: 6px; background: var(--surface); color: var(--text);
}
.ip-lineup-head { display: flex; align-items: center; justify-content: space-between; gap: 0.6rem; margin-bottom: 0.5rem; }
.ip-style { min-width: 180px; }
.ip-scope { display: flex; align-items: center; gap: 0.85rem; font-size: 0.78rem; color: var(--text-faint); margin-bottom: 0.6rem; flex-wrap: wrap; }
.ip-scope label { display: flex; align-items: center; gap: 0.3rem; cursor: pointer; }
.ip-scope-label { font-weight: 600; }
.ip-row { display: grid; grid-template-columns: 84px 1fr 1fr auto; align-items: center; gap: 0.5rem; margin-bottom: 0.4rem; }
.ip-part { font-size: 0.82rem; }
.ip-builtin { font-size: 0.78rem; color: var(--text-faint); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ip-mini {
  font-size: 0.72rem; background: none; border: 1px solid var(--border);
  border-radius: 5px; color: var(--text-faint); cursor: pointer; padding: 0.2rem 0.4rem; white-space: nowrap;
}
.ip-mini:hover { color: var(--text); }
.ip-mini-spacer { width: 0; }
.ip-slot { display: grid; grid-template-columns: 96px 1fr auto; align-items: center; gap: 0.5rem; margin-bottom: 0.3rem; }
.ip-slot-name { font-size: 0.78rem; }
.ip-audition {
  font-size: 0.7rem; line-height: 1; background: none; border: 1px solid var(--border);
  border-radius: 5px; color: var(--text-faint); cursor: pointer; padding: 0.3rem 0.45rem;
}
.ip-audition:hover { color: var(--text); border-color: var(--accent); }
.ip-add-row { display: flex; gap: 0.5rem; align-items: center; margin-bottom: 0.5rem; flex-wrap: wrap; }
.ip-add .ip-input:first-child { flex: 1; min-width: 140px; }
.ip-kind { min-width: 110px; }
.ip-file {
  font-size: 0.78rem; cursor: pointer; padding: 0.35rem 0.6rem;
  border: 1px solid var(--border); border-radius: 6px; background: var(--surface-muted);
}
.ip-file input { display: none; }
.ip-picked { font-size: 0.78rem; color: var(--text-faint); }
.ip-btn {
  font: inherit; padding: 0.4rem 0.8rem; border: 1px solid var(--border);
  border-radius: 6px; background: var(--accent); color: var(--accent-contrast, #fff); cursor: pointer;
}
.ip-btn:disabled { opacity: 0.5; cursor: default; }
.ip-err, .ip-empty { font-size: 0.8rem; color: var(--text-faint); }
.ip-err { color: #e66; }
.ip-list { list-style: none; margin: 0; padding: 0; }
.ip-item { display: flex; align-items: center; gap: 0.6rem; padding: 0.35rem 0; border-bottom: 1px solid var(--border); }
.ip-name { font-weight: 600; }
.ip-meta { font-size: 0.75rem; color: var(--text-faint); flex: 1; }
.ip-del { font-size: 0.75rem; background: none; border: 1px solid var(--border); border-radius: 5px; color: var(--text-faint); cursor: pointer; padding: 0.2rem 0.5rem; }
.ip-del:hover { color: #e66; border-color: #e66; }
</style>
