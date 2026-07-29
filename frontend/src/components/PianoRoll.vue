<!--
  GenreGrid — a style-based MIDI generator.
  Copyright (C) 2026 Tw Dover

  This program is free software: you can redistribute it and/or modify it under
  the terms of the GNU General Public License v3 or (at your option) any later
  version. Distributed WITHOUT ANY WARRANTY. See <https://www.gnu.org/licenses/>.
-->
<template>
  <canvas
    ref="canvasEl"
    class="piano-roll"
    :class="{ editable }"
    :tabindex="editable ? 0 : undefined"
    @mousedown="onPointerDown"
    @mousemove="onHover"
    @keydown="onKeyDown"
  />
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useTheme, themeColor } from '../composables/useTheme'
import * as Tone from 'tone'
import type { ParsedNote } from '../composables/useMidiPlayer'
import { scaleNotes } from '../utils/chordResolver'
import { timeAtX, pitchAtY, buildInsertedNote, nearRightEdge, resizedDuration } from '../utils/pianoRollEdit'

const props = withDefaults(defineProps<{
  notes: ParsedNote[]
  duration: number
  playing: boolean
  keyRoot?: string
  scale?: string
  editable?: boolean        // opt-in note editing (click to select, arrows to nudge)
  secondsPerBeat?: number   // seconds per beat of the file — sizes the 0.25-beat nudge
}>(), { editable: false, secondsPerBeat: 0.5 })

const emit = defineEmits<{
  (e: 'notes-changed', notes: ParsedNote[], dirty: boolean): void
}>()

const canvasEl = ref<HTMLCanvasElement | null>(null)
let rafId: number | null = null
let ro: ResizeObserver | null = null

// ── Editing state ────────────────────────────────────────────────────────────
// A local copy of the notes so edits never mutate the shared midiStore cache.
// Read-only rolls keep rendering props.notes directly — zero behavior change.
const localNotes = ref<ParsedNote[]>(props.notes.map(n => ({ ...n })))
const selectedIdx = ref<number | null>(null)
const dirty = ref(false)

// Drag-to-insert state: the note being drawn (rendered as a live preview) and the
// press position it grew from. A percussion part maps pitch → drum piece, so insert
// (which places by pitch) is disabled there — select/nudge/delete still work.
const draftNote = ref<ParsedNote | null>(null)
let insertAnchorSec = 0
let insertMidi = 60
// Resize state: grabbing a note's right edge drags its duration (start stays put).
let resizing = false
let resizeIdx = -1
const isDrumPart = computed(() => displayNotes.value.some(n => n.isPercussion))

const displayNotes = computed<ParsedNote[]>(() =>
  props.editable ? localNotes.value : props.notes)

const inScaleSet = computed<Set<number>>(() => {
  if (!props.keyRoot || !props.scale) return new Set()
  return scaleNotes(props.keyRoot, props.scale)
})

function getPitchRange() {
  const melodic = displayNotes.value.filter(n => !n.isPercussion)
  if (melodic.length === 0) return { min: 48, max: 84 }
  const min = Math.min(...melodic.map(n => n.midi))
  const max = Math.max(...melodic.map(n => n.midi))
  const pad = Math.max(2, Math.round((max - min) * 0.1))
  return { min: min - pad, max: max + pad }
}

// Pixel rect of a note — one source of truth for drawing AND click hit-testing.
function noteRect(note: ParsedNote, w: number, h: number, minP: number, pitchRange: number, dur: number) {
  const x = (note.time / dur) * w
  const noteW = Math.max(2, (note.duration / dur) * w - 1)
  if (note.isPercussion) {
    return { x, y: h - 6, w: Math.max(2, noteW * 0.3), h: 6 }
  }
  const y = h - ((note.midi - minP + 1) / pitchRange) * h
  return { x, y, w: noteW, h: Math.max(2, (h / pitchRange) * 0.85) }
}

const { theme } = useTheme()

function _rgba(token: string, alpha: number, fallback: string): string {
  const hexv = themeColor(token, fallback)
  const m = /^#([0-9a-f]{6})$/i.exec(hexv)
  if (!m) return hexv
  const n = parseInt(m[1], 16)
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`
}

function draw(playheadTime = 0) {
  const el = canvasEl.value
  if (!el) return
  const ctx = el.getContext('2d')
  if (!ctx) return

  // Canvas has no var() — resolve theme tokens once per frame
  const cBg = themeColor('--bg-deepest', '#020608')
  const cAccent = themeColor('--accent', '#00c8ff')

  const w = el.width
  const h = el.height
  const dur = props.duration || 1
  const { min: minP, max: maxP } = getPitchRange()
  const pitchRange = maxP - minP || 1

  ctx.fillStyle = cBg
  ctx.fillRect(0, 0, w, h)

  const noteH = Math.max(2, (h / pitchRange) * 0.85)
  const inScale = inScaleSet.value

  for (let p = minP; p <= maxP; p++) {
    const y = h - ((p - minP + 1) / pitchRange) * h

    // Scale row highlight
    if (inScale.size > 0 && inScale.has(p % 12)) {
      ctx.fillStyle = _rgba('--accent', 0.05, '#00c8ff')
      ctx.fillRect(0, y, w, noteH + 1)
    }

    // Pitch grid line
    ctx.strokeStyle = _rgba('--text-dim', 0.16, '#4a7080')
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.moveTo(0, y + noteH)
    ctx.lineTo(w, y + noteH)
    ctx.stroke()
  }

  for (const note of displayNotes.value) {
    const alpha = 0.45 + note.velocity * 0.55
    const r = noteRect(note, w, h, minP, pitchRange, dur)
    ctx.fillStyle = note.isPercussion
      ? _rgba('--gold', alpha, '#fbbf24')
      : _rgba('--accent', alpha, '#00c8ff')
    ctx.fillRect(r.x, r.y, r.w, r.h)
  }

  // Selected note — accent outline on top of everything
  if (props.editable && selectedIdx.value !== null) {
    const sel = displayNotes.value[selectedIdx.value]
    if (sel) {
      const r = noteRect(sel, w, h, minP, pitchRange, dur)
      ctx.strokeStyle = cAccent
      ctx.lineWidth = 2
      ctx.strokeRect(r.x - 1.5, r.y - 1.5, r.w + 3, r.h + 3)
    }
  }

  // Live insert preview — the note being dragged, before it's committed.
  if (props.editable && draftNote.value) {
    const r = noteRect(draftNote.value, w, h, minP, pitchRange, dur)
    ctx.fillStyle = _rgba('--accent', 0.85, '#00c8ff')
    ctx.fillRect(r.x, r.y, r.w, r.h)
    ctx.strokeStyle = cAccent
    ctx.lineWidth = 1.5
    ctx.strokeRect(r.x - 1, r.y - 1, r.w + 2, r.h + 2)
  }

  if (props.playing || playheadTime > 0) {
    const px = Math.min(w - 1, (playheadTime / dur) * w)
    const grad = ctx.createLinearGradient(px - 4, 0, px + 4, 0)
    grad.addColorStop(0, _rgba('--text', 0, '#e0e0e8'))
    grad.addColorStop(0.5, _rgba('--text', 0.7, '#e0e0e8'))
    grad.addColorStop(1, _rgba('--text', 0, '#e0e0e8'))
    ctx.fillStyle = grad
    ctx.fillRect(px - 4, 0, 8, h)
  }
}

function redraw() {
  draw(props.playing ? Tone.getTransport().seconds : 0)
}

// ── Editing interactions ─────────────────────────────────────────────────────

// CSS size differs from the canvas buffer size — map a pointer event into buffer pixels.
function pointerBufferXY(e: MouseEvent): { px: number; py: number } | null {
  const el = canvasEl.value
  if (!el) return null
  const rect = el.getBoundingClientRect()
  if (rect.width === 0 || rect.height === 0) return null
  return {
    px: (e.clientX - rect.left) * (el.width / rect.width),
    py: (e.clientY - rect.top) * (el.height / rect.height),
  }
}

function geometry() {
  const el = canvasEl.value!
  const dur = props.duration || 1
  const { min: minP, max: maxP } = getPitchRange()
  return { w: el.width, h: el.height, dur, minP, pitchRange: maxP - minP || 1 }
}

// Index of the topmost note under a point, or null. Topmost = last-drawn wins.
function hitTest(px: number, py: number): number | null {
  const { w, h, dur, minP, pitchRange } = geometry()
  const notes = displayNotes.value
  for (let i = notes.length - 1; i >= 0; i--) {
    const r = noteRect(notes[i], w, h, minP, pitchRange, dur)
    if (px >= r.x - 1 && px <= r.x + Math.max(3, r.w) + 1 &&
        py >= r.y - 1 && py <= r.y + r.h + 1) return i
  }
  return null
}

// mousedown: grab a note's right edge to resize, else select the note under the
// pointer, else begin a drag-to-insert (melodic parts only). A plain click with no
// drag still inserts a one-grid note.
function onPointerDown(e: MouseEvent) {
  if (!props.editable) return
  const el = canvasEl.value
  if (!el) return
  el.focus()   // capture arrow/delete keys only while the roll has focus
  const pt = pointerBufferXY(e)
  if (!pt) return

  const hit = hitTest(pt.px, pt.py)
  if (hit !== null) {
    const { w, h, dur, minP, pitchRange } = geometry()
    const r = noteRect(displayNotes.value[hit], w, h, minP, pitchRange, dur)
    if (!isDrumPart.value && nearRightEdge(pt.px, r.x, r.w)) {
      selectedIdx.value = hit
      resizeIdx = hit
      resizing = true
      e.preventDefault()
      window.addEventListener('mousemove', onResizeMove)
      window.addEventListener('mouseup', onResizeUp)
      redraw()
      return
    }
    selectedIdx.value = hit
    redraw()
    return
  }
  if (isDrumPart.value) { selectedIdx.value = null; redraw(); return }

  // Start an insert: anchor at the snapped press position/pitch and draw a preview.
  e.preventDefault()
  const { w, h, dur, minP, pitchRange } = geometry()
  insertAnchorSec = timeAtX(pt.px, w, dur)
  insertMidi = pitchAtY(pt.py, h, minP, pitchRange)
  draftNote.value = buildInsertedNote(insertAnchorSec, insertAnchorSec, insertMidi, props.secondsPerBeat)
  selectedIdx.value = null
  window.addEventListener('mousemove', onInsertMove)
  window.addEventListener('mouseup', onInsertUp)
  redraw()
}

function onInsertMove(e: MouseEvent) {
  if (!draftNote.value) return
  const pt = pointerBufferXY(e)
  if (!pt) return
  const { w, dur } = geometry()
  const endSec = timeAtX(pt.px, w, dur)
  draftNote.value = buildInsertedNote(insertAnchorSec, endSec, insertMidi, props.secondsPerBeat)
  redraw()
}

function onInsertUp() {
  window.removeEventListener('mousemove', onInsertMove)
  window.removeEventListener('mouseup', onInsertUp)
  const draft = draftNote.value
  draftNote.value = null
  if (!draft) return
  localNotes.value.push(draft)
  selectedIdx.value = localNotes.value.length - 1
  dirty.value = true
  emit('notes-changed', localNotes.value.map(x => ({ ...x })), true)
  redraw()
}

function onResizeMove(e: MouseEvent) {
  if (!resizing || resizeIdx < 0) return
  const pt = pointerBufferXY(e)
  if (!pt) return
  const n = localNotes.value[resizeIdx]
  if (!n) return
  const { w, dur } = geometry()
  n.duration = resizedDuration(n.time, timeAtX(pt.px, w, dur), props.secondsPerBeat)
  redraw()
}

function onResizeUp() {
  window.removeEventListener('mousemove', onResizeMove)
  window.removeEventListener('mouseup', onResizeUp)
  if (!resizing) return
  resizing = false
  resizeIdx = -1
  dirty.value = true
  emit('notes-changed', localNotes.value.map(x => ({ ...x })), true)
  redraw()
}

// Hover feedback: show a resize cursor when the pointer is over a note's right edge.
function onHover(e: MouseEvent) {
  const el = canvasEl.value
  if (!props.editable || !el || draftNote.value || resizing) return
  const pt = pointerBufferXY(e)
  if (!pt) return
  let onEdge = false
  const hit = hitTest(pt.px, pt.py)
  if (hit !== null && !isDrumPart.value) {
    const { w, h, dur, minP, pitchRange } = geometry()
    const r = noteRect(displayNotes.value[hit], w, h, minP, pitchRange, dur)
    onEdge = nearRightEdge(pt.px, r.x, r.w)
  }
  el.style.cursor = onEdge ? 'ew-resize' : ''
}

function onKeyDown(e: KeyboardEvent) {
  if (!props.editable || selectedIdx.value === null) return
  const notes = localNotes.value
  const n = notes[selectedIdx.value]
  if (!n) return

  if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
    const step = (e.shiftKey ? 12 : 1) * (e.key === 'ArrowUp' ? 1 : -1)
    n.midi = Math.max(0, Math.min(127, n.midi + step))
  } else if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
    const step = 0.25 * props.secondsPerBeat * (e.key === 'ArrowRight' ? 1 : -1)
    n.time = Math.max(0, n.time + step)
  } else if (e.key === 'Delete' || e.key === 'Backspace') {
    notes.splice(selectedIdx.value, 1)
    selectedIdx.value = null
  } else if (e.key === 'Escape') {
    selectedIdx.value = null
    e.preventDefault()
    redraw()
    return
  } else {
    return   // unhandled key — let it bubble (don't block typing/shortcuts)
  }

  e.preventDefault()   // arrows/backspace must not scroll or navigate the page
  dirty.value = true
  emit('notes-changed', notes.map(x => ({ ...x })), true)
  redraw()
}

/** Called by the parent after a successful save — edits are now on disk. */
function markSaved() {
  dirty.value = false
  emit('notes-changed', localNotes.value.map(x => ({ ...x })), false)
}

defineExpose({ markSaved })

// ── Rendering loop / lifecycle ───────────────────────────────────────────────

function startRaf() {
  function tick() {
    draw(Tone.getTransport().seconds)
    if (props.playing) rafId = requestAnimationFrame(tick)
  }
  rafId = requestAnimationFrame(tick)
}

function stopRaf() {
  if (rafId !== null) {
    cancelAnimationFrame(rafId)
    rafId = null
  }
}

function syncCanvasSize() {
  const el = canvasEl.value
  if (!el) return
  const { width } = el.getBoundingClientRect()
  if (width > 0 && el.width !== Math.round(width)) {
    el.width = Math.round(width)
    draw(props.playing ? Tone.getTransport().seconds : 0)
  }
}

watch(() => props.playing, (isPlaying) => {
  if (isPlaying) startRaf()
  else { stopRaf(); draw(0) }
})

// New notes from the parent (fresh fetch/parse) replace any local edits.
watch(() => props.notes, (n) => {
  localNotes.value = n.map(x => ({ ...x }))
  selectedIdx.value = null
  dirty.value = false
})

watch(() => [props.notes, props.keyRoot, props.scale], () => draw(0))
watch(theme, () => redraw())

onMounted(() => {
  syncCanvasSize()
  draw(0)
  ro = new ResizeObserver(syncCanvasSize)
  if (canvasEl.value) ro.observe(canvasEl.value)
})

onUnmounted(() => {
  stopRaf()
  ro?.disconnect()
  window.removeEventListener('mousemove', onInsertMove)
  window.removeEventListener('mouseup', onInsertUp)
  window.removeEventListener('mousemove', onResizeMove)
  window.removeEventListener('mouseup', onResizeUp)
})
</script>

<style scoped>
.piano-roll {
  display: block;
  width: 100%;
  height: 72px;
  border-radius: 5px;
  margin-top: 0.5rem;
}

.piano-roll.editable {
  cursor: pointer;
}

.piano-roll.editable:focus {
  outline: 1px solid color-mix(in srgb, var(--accent) 33%, transparent);
  outline-offset: 1px;
}
</style>
