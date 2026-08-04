<!--
  GenreGrid — a style-based MIDI generator.
  Copyright (C) 2026 Tw Dover

  This program is free software: you can redistribute it and/or modify it under
  the terms of the GNU General Public License v3 or (at your option) any later
  version. Distributed WITHOUT ANY WARRANTY. See <https://www.gnu.org/licenses/>.
-->
<!--
  One part's row on the note-region timeline strip (roadmap 9.2 follow-up) —
  a recorded MIDI take (9.1), tracked as an independent block you can drag
  along the whole song's bar range and loop, distinct from the section-block
  timeline above it (SongResult.vue's `.sr-timeline`, which only reorders/
  resizes whole generative sections). Percent-based positioning (see
  utils/noteRegionLayout.ts) rather than the section timeline's flex-basis,
  since a region can start at an arbitrary offset mid-section.
-->
<template>
  <div class="nr-track">
    <span class="nr-track-label" :title="label">{{ label }}</span>
    <div class="nr-row" ref="rowEl">
      <div
        v-for="region in regions"
        :key="region.id"
        class="nr-block"
        :class="{ 'nr-dragging': draggingId === region.id }"
        :style="rectStyle(region)"
        :title="blockTitle(region)"
        @mousedown="onDragStart(region, $event)"
      >
        <span class="nr-block-label">take{{ region.loop_count > 1 ? ` ×${region.loop_count}` : '' }}</span>
        <span class="nr-block-controls">
          <button class="nr-loop-btn" :disabled="disabled" title="Fewer repeats"
                  @click.stop="setLoop(region, region.loop_count - 1)">−</button>
          <button class="nr-loop-btn" :disabled="disabled" title="More repeats"
                  @click.stop="setLoop(region, region.loop_count + 1)">+</button>
          <button class="nr-del-btn" :disabled="disabled" title="Delete this region"
                  @click.stop="$emit('delete', region.id)">✕</button>
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { NoteRegionInfo } from '../types/midi'
import { regionRect, pxDeltaToBars, clampNewStartBar } from '../utils/noteRegionLayout'

const props = defineProps<{
  label: string
  regions: NoteRegionInfo[]
  totalBars: number
  disabled?: boolean
}>()

const emit = defineEmits<{
  (e: 'move', regionId: string, newStartBar: number): void
  (e: 'set-loop', regionId: string, loopCount: number): void
  (e: 'delete', regionId: string): void
}>()

const rowEl = ref<HTMLDivElement | null>(null)
const draggingId = ref<string | null>(null)
const previewStartBar = ref<number | null>(null)
let dragStartX = 0
let dragPxPerBar = 1
let dragOrigStartBar = 0
let dragRegion: NoteRegionInfo | null = null

function rectStyle(region: NoteRegionInfo) {
  const startBar = draggingId.value === region.id && previewStartBar.value !== null
    ? previewStartBar.value : region.start_bar
  const { leftPct, widthPct } = regionRect(startBar, region.bars, region.loop_count, props.totalBars)
  return { left: `${leftPct}%`, width: `${widthPct}%` }
}

function blockTitle(region: NoteRegionInfo): string {
  const loop = region.loop_count > 1 ? ` looped ×${region.loop_count}` : ''
  return `Recorded take, ${region.bars} bar${region.bars === 1 ? '' : 's'}${loop} — drag to move`
}

// Drag to reposition: a live percent-based preview (no request in flight)
// mirroring the section timeline's own resize-handle interaction (local
// preview state, one commit on mouseup) — but here the whole block moves
// instead of just its right edge.
function onDragStart(region: NoteRegionInfo, e: MouseEvent) {
  if (props.disabled) return
  e.preventDefault()
  const width = rowEl.value?.getBoundingClientRect().width ?? 0
  if (width <= 0 || props.totalBars <= 0) return
  draggingId.value = region.id
  dragRegion = region
  dragOrigStartBar = region.start_bar
  previewStartBar.value = region.start_bar
  dragStartX = e.clientX
  dragPxPerBar = width / props.totalBars
  window.addEventListener('mousemove', onDragMove)
  window.addEventListener('mouseup', onDragEnd)
}
function onDragMove(e: MouseEvent) {
  if (!dragRegion) return
  const deltaBars = pxDeltaToBars(e.clientX - dragStartX, dragPxPerBar)
  previewStartBar.value = clampNewStartBar(
    dragOrigStartBar + deltaBars, dragRegion.bars, dragRegion.loop_count, props.totalBars)
}
function onDragEnd() {
  window.removeEventListener('mousemove', onDragMove)
  window.removeEventListener('mouseup', onDragEnd)
  const region = dragRegion
  const newStart = previewStartBar.value
  draggingId.value = null
  previewStartBar.value = null
  dragRegion = null
  if (!region || newStart === null || newStart === dragOrigStartBar) return
  emit('move', region.id, newStart)
}

function setLoop(region: NoteRegionInfo, count: number) {
  const clamped = Math.max(1, Math.min(32, count))
  if (props.disabled || clamped === region.loop_count) return
  emit('set-loop', region.id, clamped)
}
</script>

<style scoped>
.nr-track { display: flex; align-items: center; gap: 8px; }
.nr-track-label {
  flex: 0 0 auto; width: 84px; font-size: 11px; color: var(--text-dim);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.nr-row {
  position: relative; flex: 1 1 auto; height: 26px;
  background: var(--sunken); border-radius: var(--r-sm);
}
.nr-block {
  /* A short (1-2 bar) region on a long song timeline can be just a few percent
     wide — verified live via /run-genregrid that this made the label/controls
     unreadable, so floor it at a usable pixel width regardless of percentage. */
  position: absolute; top: 2px; bottom: 2px; min-width: 88px;
  display: flex; align-items: center; justify-content: space-between; gap: 4px;
  padding: 0 6px; border-radius: var(--r-sm);
  background: var(--accent); color: var(--on-accent);
  font-size: 10px; cursor: grab; user-select: none; overflow: hidden;
}
.nr-block.nr-dragging { cursor: grabbing; opacity: 0.85; }
.nr-block-label { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.nr-block-controls { display: flex; align-items: center; gap: 2px; flex: 0 0 auto; }
.nr-loop-btn, .nr-del-btn {
  border: none; background: rgba(0, 0, 0, 0.18); color: inherit;
  border-radius: 3px; font-size: 10px; line-height: 1; padding: 2px 4px; cursor: pointer;
}
.nr-loop-btn:disabled, .nr-del-btn:disabled { opacity: 0.5; cursor: default; }
.nr-loop-btn:hover:not(:disabled), .nr-del-btn:hover:not(:disabled) { background: rgba(0, 0, 0, 0.32); }
</style>
