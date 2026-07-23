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
        <h2>Custom instruments</h2>
        <button class="ip-x" title="Close" @click="close">✕</button>
      </header>

      <p v-if="!supported()" class="ip-note">
        Custom instruments need the GenreGrid desktop app — this feature is unavailable in the browser build.
      </p>

      <template v-else>
        <!-- Add -->
        <section class="ip-add">
          <h3>Add an instrument</h3>
          <p class="ip-hint">
            Drop <strong>one sound</strong> (pitched across the keyboard), or several files named by
            note (<code>C4.wav</code>, <code>A#3.mp3</code>). Sub-folders like <code>soft/</code> and
            <code>hard/</code> become velocity layers.
          </p>
          <div class="ip-add-row">
            <input v-model="newName" class="ip-input" type="text" placeholder="Instrument name" />
            <select v-model="newKind" class="ip-input ip-kind">
              <option value="melodic">Melodic</option>
              <option value="bass">Bass</option>
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
          </div>
        </section>

        <!-- Library -->
        <section class="ip-lib">
          <h3>Your instruments ({{ instruments.length }})</h3>
          <p v-if="!instruments.length" class="ip-empty">None yet — add one above.</p>
          <ul v-else class="ip-list">
            <li v-for="inst in instruments" :key="inst.id" class="ip-item">
              <span class="ip-name">{{ inst.name }}</span>
              <span class="ip-meta">{{ inst.kind }} · {{ inst.manifest.layers.length }} layer(s)</span>
              <button class="ip-del" title="Delete" @click="remove(inst)">Delete</button>
            </li>
          </ul>
        </section>

        <!-- Per-part assignment -->
        <section class="ip-assign">
          <h3>Play these on…</h3>
          <p class="ip-hint">Pick which instrument plays each part. “Built-in” keeps the default voice/synth.</p>
          <div v-for="part in ASSIGNABLE_PARTS" :key="part" class="ip-assign-row">
            <span class="ip-part">{{ partLabel(part) }}</span>
            <select
              class="ip-input"
              :value="assignments.defaults[part] ?? ''"
              @change="onAssign(part, ($event.target as HTMLSelectElement).value)"
            >
              <option value="">Built-in</option>
              <option v-for="inst in instruments" :key="inst.id" :value="inst.id">{{ inst.name }}</option>
            </select>
          </div>
        </section>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useCustomInstruments } from '../composables/useCustomInstruments'
import type { PlayerPart } from '../composables/useMidiPlayer'
import type { CustomInstrument } from '../soundfonts/customInstruments'

const {
  instruments, assignments, panelOpen, supported,
  ensureLoaded, importInstrument, deleteInstrument, assignPart,
} = useCustomInstruments()

const ASSIGNABLE_PARTS: PlayerPart[] = ['chords', 'melody', 'arpeggio', 'bass', 'pads', 'counter_melody']
function partLabel(p: PlayerPart): string {
  return p === 'counter_melody' ? 'Counter-melody' : p.charAt(0).toUpperCase() + p.slice(1)
}

const newName = ref('')
const newKind = ref<'melodic' | 'bass'>('melodic')
const picked = ref<File[]>([])
const filesInput = ref<HTMLInputElement | null>(null)
const folderInput = ref<HTMLInputElement | null>(null)
const importing = ref(false)
const error = ref('')

const pickedCount = computed(() => picked.value.length)
const canImport = computed(() => picked.value.length > 0 && newName.value.trim().length > 0)

watch(panelOpen, (open) => { if (open) ensureLoaded() })

function onPick(e: Event) {
  const input = e.target as HTMLInputElement
  picked.value = input.files ? Array.from(input.files) : []
  error.value = ''
}

async function doImport() {
  if (!canImport.value) return
  importing.value = true
  error.value = ''
  try {
    const inst = await importInstrument(newName.value, newKind.value, picked.value)
    if (!inst) { error.value = 'No usable audio files found.'; return }
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
}

function onAssign(part: PlayerPart, id: string) {
  assignPart(part, id || null)
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
  width: min(560px, 100%); max-height: 86vh; overflow: auto;
  padding: 1rem 1.25rem;
}
.ip-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.5rem; }
.ip-header h2 { margin: 0; font-size: 1.1rem; }
.ip-x { background: none; border: none; color: var(--text-faint); cursor: pointer; font-size: 1rem; }
.ip-x:hover { color: var(--text); }
.ip-note { color: var(--text-faint); }
section { border-top: 1px solid var(--border); padding-top: 0.85rem; margin-top: 0.85rem; }
h3 { font-size: 0.85rem; margin: 0 0 0.4rem; color: var(--text); }
.ip-hint { font-size: 0.78rem; color: var(--text-faint); margin: 0 0 0.6rem; }
.ip-hint code { background: var(--surface-muted); padding: 0 0.25rem; border-radius: 3px; }
.ip-add-row { display: flex; gap: 0.5rem; align-items: center; margin-bottom: 0.5rem; flex-wrap: wrap; }
.ip-input {
  font: inherit; padding: 0.35rem 0.5rem; border: 1px solid var(--border);
  border-radius: 6px; background: var(--surface); color: var(--text);
}
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
.ip-assign-row { display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.4rem; }
.ip-part { width: 120px; font-size: 0.82rem; }
.ip-assign-row .ip-input { flex: 1; }
</style>
