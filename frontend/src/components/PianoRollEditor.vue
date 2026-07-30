<!--
  GenreGrid — a style-based MIDI generator.
  Copyright (C) 2026 Tw Dover

  This program is free software: you can redistribute it and/or modify it under
  the terms of the GNU General Public License v3 or (at your option) any later
  version. Distributed WITHOUT ANY WARRANTY. See <https://www.gnu.org/licenses/>.
-->
<!--
  A full-screen, zoomable piano-roll editor. Unlike the inline PianoRoll (a 72px
  fit-to-width preview), this draws at an explicit scale with a piano-keyboard
  gutter, a bar/beat ruler, a snap grid, a velocity lane, marquee multi-select,
  and scroll + zoom — so notes can actually be placed, sized, and shaped precisely.
  Shares the pure note↔pixel math in utils/pianoRollEdit.ts; emits the same
  `notes-changed` contract as PianoRoll so the parent's save path is reused.
-->
<template>
  <div class="pre-overlay" @mousedown.self="$emit('close')">
    <div class="pre-modal" role="dialog" aria-label="Piano-roll editor">
      <div class="pre-header">
        <span class="pre-title">Edit <span class="pre-part">{{ partName }}</span></span>
        <span class="pre-meta">{{ keyRoot }} {{ scale }} · {{ Math.round(60 / secondsPerBeat) }} BPM</span>
        <button class="pre-x" @click="$emit('close')" title="Close editor">✕</button>
      </div>

      <div class="pre-toolbar">
        <button class="pre-btn pre-play" @click="togglePlay" :title="playing ? 'Stop' : (loopStartBeat !== null ? 'Play the loop region' : 'Play this part')">
          {{ playing ? '■' : '▶' }}
        </button>
        <button v-if="loopStartBeat !== null" class="pre-btn pre-loopclear" @click="clearLoop" title="Clear the loop region">Loop ✕</button>
        <div class="pre-group" title="Tool — Draw adds notes, Select marquees a group" v-if="!isDrumPart">
          <button class="pre-btn pre-tool" :class="{ active: tool === 'draw' }" @click="tool = 'draw'" title="Draw notes (drag empty grid to add)">✏ Draw</button>
          <button class="pre-btn pre-tool" :class="{ active: tool === 'select' }" @click="tool = 'select'" title="Select (drag empty grid to marquee-select a group)">▭ Select</button>
        </div>
        <div class="pre-group">
          <span class="pre-glabel">Zoom</span>
          <span class="pre-axis" title="Zoom time (horizontal)">↔</span>
          <button class="pre-btn" @click="zoomH(1 / 1.4)" :disabled="pxPerBeat <= MIN_PXB" title="Zoom out — time (show more bars)">−</button>
          <button class="pre-btn" @click="zoomH(1.4)" :disabled="pxPerBeat >= MAX_PXB" title="Zoom in — time (fewer bars, wider)">+</button>
          <span class="pre-axis" title="Zoom pitch (vertical)">↕</span>
          <button class="pre-btn" @click="zoomV(1 / 1.3)" :disabled="pxPerSemitone <= MIN_PXS" title="Zoom out — pitch (shorter rows)">−</button>
          <button class="pre-btn" @click="zoomV(1.3)" :disabled="pxPerSemitone >= MAX_PXS" title="Zoom in — pitch (taller rows)">+</button>
        </div>
        <button class="pre-btn pre-fit" @click="fit" title="Fit the whole part in view">Fit</button>
        <label class="pre-snap" title="Snap notes to this grid">
          Snap
          <select v-model.number="division">
            <option :value="1">1/4</option>
            <option :value="0.5">1/8</option>
            <option :value="0.25">1/16</option>
            <option :value="0.125">1/32</option>
          </select>
        </label>
        <span v-if="selected.size > 1" class="pre-selcount">{{ selected.size }} selected</span>
        <span class="pre-spacer-flex" />
        <button
          class="pre-btn pre-save"
          :disabled="!dirty"
          @click="$emit('save')"
          :title="dirty ? 'Write note edits into the stem and rebuild song.mid' : 'No unsaved edits'"
        >Save edits</button>
      </div>

      <div ref="viewportEl" class="pre-viewport">
        <canvas
          ref="canvasEl"
          class="pre-canvas"
          tabindex="0"
          @mousedown="onPointerDown"
          @mousemove="onHover"
          @wheel="onWheel"
          @keydown="onKeyDown"
        />
      </div>

      <div class="pre-hint">
        <template v-if="isDrumPart">▶ plays this part · drag the ruler to set a loop region, drag a flag to move one edge · click a hit to select · arrows to nudge · ⌫ to delete · drag the velocity lane to shape dynamics · ⌘/Ctrl-scroll to zoom</template>
        <template v-else>▶ plays what you hear · click a key (left) or place a note to preview its sound · drag the ruler to loop a span, drag a ⟑ flag to move one edge · Draw: drag empty grid to add, drag a note's right edge to resize · Select: marquee a group, Shift-click to extend, drag to move · arrows to nudge (Shift = octave / bar) · ⌫ to delete · drag the velocity lane · ⌘/Ctrl-scroll to zoom</template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import * as Tone from 'tone'
import { Midi } from '@tonejs/midi'
import { useTheme, themeColor } from '../composables/useTheme'
import { useMidiPlayer, type ParsedNote } from '../composables/useMidiPlayer'
import { CHANNEL_PART, type PlayerPart } from '../composables/playerConstants'
import { scaleNotes } from '../utils/chordResolver'
import {
  buildInsertedNote, nearRightEdge, resizedDuration, midiToNoteName, isBlackKey,
  noteRectZoom, beatToX, timeToX, xToTime, yToPitch, velocityFromLaneY, snapDelta, rectsOverlap,
  nearLoopFlag, sanitizeNotesForPlayback, type RollViewport,
} from '../utils/pianoRollEdit'

const props = withDefaults(defineProps<{
  notes: ParsedNote[]
  duration: number
  secondsPerBeat?: number
  keyRoot?: string
  scale?: string
  partName?: string
  styleId?: string
}>(), { secondsPerBeat: 0.5, partName: 'part' })

const emit = defineEmits<{
  (e: 'notes-changed', notes: ParsedNote[], dirty: boolean): void
  (e: 'save'): void
  (e: 'close'): void
}>()

const GUTTER_W = 54
const RULER_H = 26
const SB = 12                 // scrollbar thickness
const VELO_H = 68             // velocity lane height
const MIN_PXB = 12, MAX_PXB = 220
const MIN_PXS = 7, MAX_PXS = 34

const canvasEl = ref<HTMLCanvasElement | null>(null)
const viewportEl = ref<HTMLDivElement | null>(null)
let ro: ResizeObserver | null = null

const localNotes = ref<ParsedNote[]>(props.notes.map(n => ({ ...n })))
// Selection holds note *references* into localNotes, so it survives in-place moves and
// velocity edits (indices would shift on insert/delete).
const selected = ref<Set<ParsedNote>>(new Set())
const dirty = ref(false)
const division = ref(0.25)
const tool = ref<'draw' | 'select'>('draw')

const pxPerBeat = ref(48)
const pxPerSemitone = ref(15)
const scrollX = ref(0)
const scrollY = ref(0)

// Playback + audition (hear what you're editing).
const player = useMidiPlayer()
const partChannel = computed(() => {
  for (const [ch, p] of Object.entries(CHANNEL_PART)) if (p === props.partName) return Number(ch)
  return 0
})
const partForAudio = computed<PlayerPart>(() => (CHANNEL_PART[partChannel.value] ?? 'chords'))
let blobUrl: string | null = null
const playing = ref(false)
const playheadSec = ref(0)
let phRaf: number | null = null
// Loop region in beats (null = play through once). Snapped to the grid on drag.
const loopStartBeat = ref<number | null>(null)
const loopEndBeat = ref<number | null>(null)

const isDrumPart = computed(() => localNotes.value.some(n => n.isPercussion))
const secPerBeat = computed(() => props.secondsPerBeat || 0.5)

const BEATS_PER_BAR = 4
const totalBeats = computed(() => {
  const byDur = props.duration / secPerBeat.value
  const byNotes = localNotes.value.reduce((m, n) => Math.max(m, (n.time + n.duration) / secPerBeat.value), 0)
  const raw = Math.max(byDur, byNotes, BEATS_PER_BAR)
  return Math.ceil(raw / BEATS_PER_BAR) * BEATS_PER_BAR + BEATS_PER_BAR
})

const pitchSpan = computed(() => {
  const melodic = localNotes.value.filter(n => !n.isPercussion)
  if (melodic.length === 0) return { top: 84, bottom: 48 }
  const hi = Math.max(...melodic.map(n => n.midi))
  const lo = Math.min(...melodic.map(n => n.midi))
  return { top: Math.min(127, hi + 4), bottom: Math.max(0, lo - 4) }
})
const pitchCount = computed(() => pitchSpan.value.top - pitchSpan.value.bottom + 1)

const inScaleSet = computed<Set<number>>(() => {
  if (!props.keyRoot || !props.scale) return new Set()
  return scaleNotes(props.keyRoot, props.scale)
})

function gridSize() {
  const el = canvasEl.value
  if (!el) return { w: 0, h: 0, gw: 0, gh: 0 }
  const w = el.width, h = el.height
  return { w, h, gw: Math.max(1, w - GUTTER_W - SB), gh: Math.max(1, h - RULER_H - SB - VELO_H) }
}
const contentW = computed(() => totalBeats.value * pxPerBeat.value)
const contentH = computed(() => pitchCount.value * pxPerSemitone.value)

function veloTop() { const { gh } = gridSize(); return RULER_H + gh }   // lane sits under the grid

function clampScroll() {
  const { gw, gh } = gridSize()
  scrollX.value = Math.max(0, Math.min(scrollX.value, Math.max(0, contentW.value - gw)))
  scrollY.value = Math.max(0, Math.min(scrollY.value, Math.max(0, contentH.value - gh)))
}

function viewport(): RollViewport {
  return {
    pxPerBeat: pxPerBeat.value, pxPerSemitone: pxPerSemitone.value,
    scrollX: scrollX.value, scrollY: scrollY.value,
    topPitch: pitchSpan.value.top, secondsPerBeat: secPerBeat.value,
    gutterW: GUTTER_W, rulerH: RULER_H,
  }
}

// ── Drawing ────────────────────────────────────────────────────────────────
const { theme } = useTheme()

function _rgba(token: string, alpha: number, fallback: string): string {
  const hexv = themeColor(token, fallback)
  const m = /^#([0-9a-f]{6})$/i.exec(hexv)
  if (!m) return hexv
  const n = parseInt(m[1], 16)
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`
}

const draftNote = ref<ParsedNote | null>(null)
const marquee = ref<{ x0: number; y0: number; x1: number; y1: number } | null>(null)

function draw() {
  const el = canvasEl.value
  if (!el) return
  const ctx = el.getContext('2d')
  if (!ctx) return
  const { w, h, gw, gh } = gridSize()
  const vp = viewport()
  const cBg = themeColor('--bg-deepest', '#020608')
  const cPanel = themeColor('--panel', '#0e1a20')
  const cAccent = themeColor('--accent', '#00c8ff')

  ctx.clearRect(0, 0, w, h)
  ctx.fillStyle = cBg
  ctx.fillRect(GUTTER_W, RULER_H, gw, gh)

  const gridRight = GUTTER_W + gw
  const gridBottom = RULER_H + gh

  // ── Note grid (clipped) ──
  ctx.save()
  ctx.beginPath(); ctx.rect(GUTTER_W, RULER_H, gw, gh); ctx.clip()

  for (let p = pitchSpan.value.bottom; p <= pitchSpan.value.top; p++) {
    const y = RULER_H - scrollY.value + (pitchSpan.value.top - p) * pxPerSemitone.value
    if (y > gridBottom || y + pxPerSemitone.value < RULER_H) continue
    if (isBlackKey(p)) {
      ctx.fillStyle = _rgba('--text-dim', 0.06, '#4a7080')
      ctx.fillRect(GUTTER_W, y, gw, pxPerSemitone.value)
    }
    if (inScaleSet.value.size > 0 && inScaleSet.value.has(p % 12)) {
      ctx.fillStyle = _rgba('--accent', 0.05, '#00c8ff')
      ctx.fillRect(GUTTER_W, y, gw, pxPerSemitone.value)
    }
    ctx.strokeStyle = _rgba('--text-dim', p % 12 === 0 ? 0.28 : 0.1, '#4a7080')
    ctx.lineWidth = 1
    ctx.beginPath(); ctx.moveTo(GUTTER_W, y); ctx.lineTo(gridRight, y); ctx.stroke()
  }

  const div = division.value
  const showSubs = div * pxPerBeat.value >= 6
  const step = showSubs ? div : 1
  const firstBeat = scrollX.value / pxPerBeat.value
  const lastBeat = (scrollX.value + gw) / pxPerBeat.value
  for (let idx = Math.floor(firstBeat / step); idx <= Math.ceil(lastBeat / step); idx++) {
    const beat = idx * step
    const x = GUTTER_W - scrollX.value + beat * pxPerBeat.value
    if (x < GUTTER_W - 0.5 || x > gridRight) continue
    const isBar = Math.abs(beat % BEATS_PER_BAR) < 1e-6
    const isBeat = Math.abs(beat % 1) < 1e-6
    ctx.strokeStyle = _rgba('--text-dim', isBar ? 0.4 : isBeat ? 0.22 : 0.09, '#4a7080')
    ctx.lineWidth = 1
    ctx.beginPath(); ctx.moveTo(x, RULER_H); ctx.lineTo(x, gridBottom); ctx.stroke()
  }

  // Loop region band (behind the notes)
  if (loopStartBeat.value !== null && loopEndBeat.value !== null) {
    const lx0 = beatToX(Math.min(loopStartBeat.value, loopEndBeat.value), vp)
    const lx1 = beatToX(Math.max(loopStartBeat.value, loopEndBeat.value), vp)
    ctx.fillStyle = _rgba('--good', 0.1, '#4ade80')
    ctx.fillRect(lx0, RULER_H, lx1 - lx0, gh)
    ctx.strokeStyle = _rgba('--good', 0.6, '#4ade80'); ctx.lineWidth = 1
    ctx.beginPath(); ctx.moveTo(lx0, RULER_H); ctx.lineTo(lx0, gridBottom)
    ctx.moveTo(lx1, RULER_H); ctx.lineTo(lx1, gridBottom); ctx.stroke()
  }

  for (const note of localNotes.value) {
    const r = noteRectZoom(note, vp)
    if (r.x > gridRight || r.x + r.w < GUTTER_W || r.y > gridBottom || r.y + r.h < RULER_H) continue
    const alpha = 0.5 + note.velocity * 0.5
    ctx.fillStyle = note.isPercussion ? _rgba('--gold', alpha, '#fbbf24') : _rgba('--accent', alpha, '#00c8ff')
    ctx.fillRect(r.x, r.y, r.w, r.h)
    if (selected.value.has(note)) {
      ctx.strokeStyle = cAccent; ctx.lineWidth = 2
      ctx.strokeRect(r.x - 1, r.y - 1, r.w + 2, r.h + 2)
    }
  }

  if (draftNote.value) {
    const r = noteRectZoom(draftNote.value, vp)
    ctx.fillStyle = _rgba('--accent', 0.85, '#00c8ff')
    ctx.fillRect(r.x, r.y, r.w, r.h)
    ctx.strokeStyle = cAccent; ctx.lineWidth = 1.5
    ctx.strokeRect(r.x - 1, r.y - 1, r.w + 2, r.h + 2)
  }

  // Marquee box
  if (marquee.value) {
    const { x0, y0, x1, y1 } = marquee.value
    const mx = Math.min(x0, x1), my = Math.min(y0, y1)
    ctx.fillStyle = _rgba('--accent', 0.12, '#00c8ff')
    ctx.fillRect(mx, my, Math.abs(x1 - x0), Math.abs(y1 - y0))
    ctx.strokeStyle = _rgba('--accent', 0.7, '#00c8ff'); ctx.lineWidth = 1
    ctx.strokeRect(mx, my, Math.abs(x1 - x0), Math.abs(y1 - y0))
  }

  // Playhead (on top of everything in the grid)
  if (playing.value) {
    const px = timeToX(playheadSec.value, vp)
    if (px >= GUTTER_W && px <= gridRight) {
      ctx.fillStyle = _rgba('--text', 0.85, '#e0e0e8')
      ctx.fillRect(px - 1, RULER_H, 2, gh)
    }
  }
  ctx.restore()

  drawVelocityLane(ctx, cPanel, cAccent, gw, gh)

  // ── Keyboard gutter ──
  ctx.fillStyle = cPanel
  ctx.fillRect(0, RULER_H, GUTTER_W, gh)
  ctx.save()
  ctx.beginPath(); ctx.rect(0, RULER_H, GUTTER_W, gh); ctx.clip()
  ctx.font = '10px system-ui, sans-serif'
  ctx.textBaseline = 'middle'
  for (let p = pitchSpan.value.bottom; p <= pitchSpan.value.top; p++) {
    const y = RULER_H - scrollY.value + (pitchSpan.value.top - p) * pxPerSemitone.value
    if (y > gridBottom || y + pxPerSemitone.value < RULER_H) continue
    ctx.fillStyle = isBlackKey(p) ? _rgba('--text-dim', 0.5, '#4a7080') : _rgba('--text', 0.9, '#e0e0e8')
    ctx.fillRect(1, y + 0.5, GUTTER_W - 2, pxPerSemitone.value - 1)
    if (p % 12 === 0 || pxPerSemitone.value >= 12) {
      ctx.fillStyle = isBlackKey(p) ? _rgba('--text', 0.85, '#e0e0e8') : themeColor('--bg-deepest', '#020608')
      ctx.fillText(midiToNoteName(p), 4, y + pxPerSemitone.value / 2)
    }
  }
  ctx.restore()

  // ── Ruler ──
  ctx.fillStyle = cPanel
  ctx.fillRect(0, 0, w, RULER_H)
  ctx.save()
  ctx.beginPath(); ctx.rect(GUTTER_W, 0, gw, RULER_H); ctx.clip()
  // Loop span + draggable start/end flags in the ruler.
  if (loopStartBeat.value !== null && loopEndBeat.value !== null) {
    const lx0 = beatToX(Math.min(loopStartBeat.value, loopEndBeat.value), vp)
    const lx1 = beatToX(Math.max(loopStartBeat.value, loopEndBeat.value), vp)
    ctx.fillStyle = _rgba('--good', 0.55, '#4ade80')
    ctx.fillRect(lx0, RULER_H - 4, Math.max(2, lx1 - lx0), 4)
    // Flag handles: a small triangular tab at each boundary (grab to move one edge).
    const flag = (x: number, dir: 1 | -1) => {
      ctx.fillStyle = _rgba('--good', 1, '#4ade80')
      ctx.beginPath()
      ctx.moveTo(x, 2); ctx.lineTo(x, RULER_H - 2)
      ctx.lineTo(x + dir * 7, RULER_H / 2 - 1); ctx.closePath(); ctx.fill()
    }
    flag(lx0, 1)     // start flag points right, into the region
    flag(lx1, -1)    // end flag points left
  }
  ctx.font = '10px system-ui, sans-serif'
  ctx.textBaseline = 'middle'
  ctx.fillStyle = _rgba('--text', 0.7, '#e0e0e8')
  const firstBar = Math.floor(scrollX.value / (BEATS_PER_BAR * pxPerBeat.value))
  const lastBar = Math.ceil((scrollX.value + gw) / (BEATS_PER_BAR * pxPerBeat.value))
  for (let bar = firstBar; bar <= lastBar; bar++) {
    const x = GUTTER_W - scrollX.value + bar * BEATS_PER_BAR * pxPerBeat.value
    if (x < GUTTER_W - 1 || x > gridRight) continue
    ctx.strokeStyle = _rgba('--text-dim', 0.4, '#4a7080')
    ctx.beginPath(); ctx.moveTo(x, 4); ctx.lineTo(x, RULER_H); ctx.stroke()
    ctx.fillText(String(bar + 1), x + 3, RULER_H / 2)
  }
  ctx.restore()

  // Corner + border
  ctx.fillStyle = cPanel
  ctx.fillRect(0, 0, GUTTER_W, RULER_H)
  ctx.strokeStyle = _rgba('--text-dim', 0.25, '#4a7080')
  ctx.lineWidth = 1
  ctx.strokeRect(0.5, 0.5, w - 1, h - 1)

  drawScrollbar(ctx, 'h', gw, gh)
  drawScrollbar(ctx, 'v', gw, gh)
}

function drawVelocityLane(ctx: CanvasRenderingContext2D, cPanel: string, cAccent: string, gw: number, gh: number) {
  const top = RULER_H + gh
  // Gutter label
  ctx.fillStyle = cPanel
  ctx.fillRect(0, top, GUTTER_W, VELO_H)
  ctx.font = '9px system-ui, sans-serif'
  ctx.textBaseline = 'middle'
  ctx.fillStyle = _rgba('--text-faint', 1, '#6a8a98')
  ctx.save(); ctx.translate(GUTTER_W / 2, top + VELO_H / 2); ctx.rotate(0)
  ctx.textAlign = 'center'; ctx.fillText('vel', 0, 0); ctx.textAlign = 'start'
  ctx.restore()

  ctx.fillStyle = themeColor('--bg-deepest', '#020608')
  ctx.fillRect(GUTTER_W, top, gw, VELO_H)
  ctx.strokeStyle = _rgba('--text-dim', 0.3, '#4a7080'); ctx.lineWidth = 1
  ctx.beginPath(); ctx.moveTo(GUTTER_W, top + 0.5); ctx.lineTo(GUTTER_W + gw, top + 0.5); ctx.stroke()

  ctx.save()
  ctx.beginPath(); ctx.rect(GUTTER_W, top, gw, VELO_H); ctx.clip()
  const vp = viewport()
  const gridRight = GUTTER_W + gw
  for (const note of localNotes.value) {
    const r = noteRectZoom(note, vp)
    const cx = r.x
    if (cx < GUTTER_W - 4 || cx > gridRight) continue
    const barH = note.velocity * (VELO_H - 6)
    const barW = Math.max(3, Math.min(r.w, 10))
    const sel = selected.value.has(note)
    ctx.fillStyle = sel ? cAccent : (note.isPercussion ? _rgba('--gold', 0.8, '#fbbf24') : _rgba('--accent', 0.65, '#00c8ff'))
    ctx.fillRect(cx, top + VELO_H - 3 - barH, barW, barH)
  }
  ctx.restore()
}

function drawScrollbar(ctx: CanvasRenderingContext2D, axis: 'h' | 'v', gw: number, gh: number) {
  const { w, h } = gridSize()
  ctx.fillStyle = _rgba('--panel', 1, '#0e1a20')
  if (axis === 'h') {
    ctx.fillRect(GUTTER_W, h - SB, gw, SB)
    if (contentW.value <= gw) return
    const thumbW = Math.max(24, (gw / contentW.value) * gw)
    const x = GUTTER_W + (scrollX.value / (contentW.value - gw)) * (gw - thumbW)
    ctx.fillStyle = _rgba('--text-dim', 0.5, '#4a7080')
    roundRect(ctx, x + 1, h - SB + 2, thumbW - 2, SB - 4, 3)
  } else {
    ctx.fillRect(w - SB, RULER_H, SB, gh)
    if (contentH.value <= gh) return
    const thumbH = Math.max(24, (gh / contentH.value) * gh)
    const y = RULER_H + (scrollY.value / (contentH.value - gh)) * (gh - thumbH)
    ctx.fillStyle = _rgba('--text-dim', 0.5, '#4a7080')
    roundRect(ctx, w - SB + 2, y + 1, SB - 4, thumbH - 2, 3)
  }
}

function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath(); ctx.roundRect(x, y, w, h, r); ctx.fill()
}

function redraw() { clampScroll(); draw() }

// ── Interaction ──────────────────────────────────────────────────────────────
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

function inGrid(px: number, py: number): boolean {
  const { w, gh } = gridSize()
  return px >= GUTTER_W && px <= w - SB && py >= RULER_H && py <= RULER_H + gh
}
function inVelocityLane(px: number, py: number): boolean {
  const { w } = gridSize()
  const top = veloTop()
  return px >= GUTTER_W && px <= w - SB && py >= top && py <= top + VELO_H
}

function hitTest(px: number, py: number): number | null {
  const vp = viewport()
  for (let i = localNotes.value.length - 1; i >= 0; i--) {
    const r = noteRectZoom(localNotes.value[i], vp)
    if (px >= r.x - 1 && px <= r.x + Math.max(3, r.w) + 1 && py >= r.y - 1 && py <= r.y + r.h + 1) return i
  }
  return null
}
/** Topmost note whose horizontal span covers px (for the velocity lane). */
function noteAtX(px: number): ParsedNote | null {
  const vp = viewport()
  for (let i = localNotes.value.length - 1; i >= 0; i--) {
    const r = noteRectZoom(localNotes.value[i], vp)
    if (px >= r.x - 4 && px <= r.x + Math.max(4, r.w) + 2) return localNotes.value[i]
  }
  return null
}

let resizing = false
let resizeIdx = -1
let insertAnchorSec = 0
let insertMidi = 60
let sbDrag: 'h' | 'v' | null = null
// Group move
let moveOrigin = { sec: 0, midi: 60 }
let moveSnapshot: Map<ParsedNote, { time: number; midi: number }> | null = null
let moved = false
let collapseOnClick: ParsedNote | null = null
// Velocity paint
let veloTargets: ParsedNote[] | null = null   // when a multi-selection is dragged together
// Loop-region drag. `loopEdge` = which boundary flag is being dragged (null = a fresh
// span drag); `loopAnchorBeat` is the fixed edge/anchor the moving edge is measured against.
let loopAnchorBeat = 0
let loopEdge: 'start' | 'end' | null = null

function beatAtX(px: number): number { return xToTime(px, viewport()) / secPerBeat.value }
function snapBeat(beat: number): number { return Math.max(0, Math.round(beat / division.value) * division.value) }

function selectOnly(note: ParsedNote) { selected.value = new Set([note]) }
function toggleSel(note: ParsedNote) {
  const s = new Set(selected.value)
  if (s.has(note)) s.delete(note)
  else s.add(note)
  selected.value = s
}

function onPointerDown(e: MouseEvent) {
  const el = canvasEl.value
  if (!el) return
  el.focus()
  const pt = pointerBufferXY(e)
  if (!pt) return
  const { w, h } = gridSize()

  // Scrollbars
  if (pt.py >= h - SB && pt.px >= GUTTER_W && pt.px <= w - SB && contentW.value > w - GUTTER_W - SB) {
    sbDrag = 'h'; e.preventDefault()
    window.addEventListener('mousemove', onSbMove); window.addEventListener('mouseup', onSbUp)
    onSbMove(e); return
  }
  if (pt.px >= w - SB && pt.py >= RULER_H && pt.py <= veloTop() && contentH.value > h - RULER_H - SB - VELO_H) {
    sbDrag = 'v'; e.preventDefault()
    window.addEventListener('mousemove', onSbMove); window.addEventListener('mouseup', onSbUp)
    onSbMove(e); return
  }

  // Velocity lane
  if (inVelocityLane(pt.px, pt.py)) {
    const note = noteAtX(pt.px)
    if (note) {
      e.preventDefault()
      // Dragging a bar that belongs to a multi-selection sets the whole group;
      // otherwise it paints individual notes under the cursor.
      veloTargets = selected.value.has(note) && selected.value.size > 1 ? [...selected.value] : null
      applyVelocity(pt.px, pt.py)
      window.addEventListener('mousemove', onVeloMove); window.addEventListener('mouseup', onVeloUp)
    }
    return
  }

  // Ruler → grab an existing loop flag to move one edge, else drag out a new region.
  if (pt.py < RULER_H && pt.px >= GUTTER_W && pt.px <= w - SB) {
    e.preventDefault()
    const vp = viewport()
    // Grab a start/end flag if the press is on one (edges drag independently).
    if (loopStartBeat.value !== null && loopEndBeat.value !== null) {
      const sx = beatToX(loopStartBeat.value, vp)
      const ex = beatToX(loopEndBeat.value, vp)
      if (nearLoopFlag(pt.px, ex)) { loopEdge = 'end'; loopAnchorBeat = loopStartBeat.value }
      else if (nearLoopFlag(pt.px, sx)) { loopEdge = 'start'; loopAnchorBeat = loopEndBeat.value }
    }
    if (loopEdge === null) {
      // Fresh region: anchor here and drag out.
      const beat = snapBeat(beatAtX(pt.px))
      loopStartBeat.value = beat
      loopEndBeat.value = beat
      loopAnchorBeat = beat
    }
    window.addEventListener('mousemove', onLoopMove); window.addEventListener('mouseup', onLoopUp)
    redraw(); return
  }

  // Keyboard gutter → audition the pitch of the clicked key (no edit).
  if (pt.px < GUTTER_W && pt.py >= RULER_H && pt.py <= veloTop() && !isDrumPart.value) {
    audition(yToPitch(pt.py, viewport()))
    return
  }

  if (!inGrid(pt.px, pt.py)) return

  const hit = hitTest(pt.px, pt.py)
  if (hit !== null) {
    const note = localNotes.value[hit]
    const r = noteRectZoom(note, viewport())
    // Right-edge resize (single note, melodic only)
    if (!isDrumPart.value && nearRightEdge(pt.px, r.x, r.w)) {
      selectOnly(note); resizeIdx = hit; resizing = true
      e.preventDefault()
      window.addEventListener('mousemove', onResizeMove); window.addEventListener('mouseup', onResizeUp)
      redraw(); return
    }
    // Selection + arm a group move.
    if (e.shiftKey) {
      toggleSel(note); collapseOnClick = null
    } else if (selected.value.has(note)) {
      collapseOnClick = note                 // keep the group; collapse on a click w/o drag
    } else {
      selectOnly(note); collapseOnClick = null
      audition(note.midi)                    // hear the note you just selected
    }
    if (selected.value.has(note)) {
      const vp = viewport()
      moveOrigin = { sec: xToTime(pt.px, vp), midi: yToPitch(pt.py, vp) }
      moveSnapshot = new Map()
      for (const n of selected.value) moveSnapshot.set(n, { time: n.time, midi: n.midi })
      moved = false
      e.preventDefault()
      window.addEventListener('mousemove', onMoveMove); window.addEventListener('mouseup', onMoveUp)
    }
    redraw(); return
  }

  // Empty grid: marquee (Select tool or drums) or insert (Draw tool, melodic).
  if (tool.value === 'select' || isDrumPart.value) {
    if (!e.shiftKey) selected.value = new Set()
    marquee.value = { x0: pt.px, y0: pt.py, x1: pt.px, y1: pt.py }
    e.preventDefault()
    window.addEventListener('mousemove', onMarqueeMove); window.addEventListener('mouseup', onMarqueeUp)
    redraw(); return
  }

  // Draw tool, empty grid → insert.
  e.preventDefault()
  const vp = viewport()
  insertAnchorSec = xToTime(pt.px, vp)
  insertMidi = yToPitch(pt.py, vp)
  draftNote.value = buildInsertedNote(insertAnchorSec, insertAnchorSec, insertMidi, secPerBeat.value, 0.7, division.value)
  selected.value = new Set()
  window.addEventListener('mousemove', onInsertMove); window.addEventListener('mouseup', onInsertUp)
  redraw()
}

// Insert
function onInsertMove(e: MouseEvent) {
  if (!draftNote.value) return
  const pt = pointerBufferXY(e); if (!pt) return
  draftNote.value = buildInsertedNote(insertAnchorSec, xToTime(pt.px, viewport()), insertMidi, secPerBeat.value, 0.7, division.value)
  redraw()
}
function onInsertUp() {
  window.removeEventListener('mousemove', onInsertMove); window.removeEventListener('mouseup', onInsertUp)
  const draft = draftNote.value; draftNote.value = null
  if (!draft) return
  localNotes.value.push(draft)
  selectOnly(draft)
  audition(draft.midi)     // hear the note you just placed
  commit()
}

// Loop region drag (in the ruler)
function onLoopMove(e: MouseEvent) {
  const pt = pointerBufferXY(e); if (!pt) return
  const beat = snapBeat(beatAtX(pt.px))
  loopStartBeat.value = Math.min(loopAnchorBeat, beat)
  loopEndBeat.value = Math.max(loopAnchorBeat, beat)
  syncLoopToTransport()
  redraw()
}
function onLoopUp() {
  window.removeEventListener('mousemove', onLoopMove); window.removeEventListener('mouseup', onLoopUp)
  // A fresh click with no drag (zero-width span) clears the loop instead of setting one.
  // Grabbing a flag (loopEdge set) never collapses to zero here, so it's left intact.
  if (loopEdge === null && loopStartBeat.value !== null && loopEndBeat.value !== null
      && Math.abs(loopEndBeat.value - loopStartBeat.value) < 1e-6) {
    clearLoop()
  }
  loopEdge = null
  syncLoopToTransport()
  redraw()
}

// Resize
function onResizeMove(e: MouseEvent) {
  if (!resizing || resizeIdx < 0) return
  const pt = pointerBufferXY(e); if (!pt) return
  const n = localNotes.value[resizeIdx]; if (!n) return
  n.duration = resizedDuration(n.time, xToTime(pt.px, viewport()), secPerBeat.value, division.value)
  redraw()
}
function onResizeUp() {
  window.removeEventListener('mousemove', onResizeMove); window.removeEventListener('mouseup', onResizeUp)
  if (!resizing) return
  resizing = false; resizeIdx = -1
  commit()
}

// Group move
function onMoveMove(e: MouseEvent) {
  if (!moveSnapshot) return
  const pt = pointerBufferXY(e); if (!pt) return
  const vp = viewport()
  const dSec = snapDelta(xToTime(pt.px, vp) - moveOrigin.sec, secPerBeat.value, division.value)
  const dMidi = isDrumPart.value ? 0 : Math.round(yToPitch(pt.py, vp) - moveOrigin.midi)
  if (dSec !== 0 || dMidi !== 0) moved = true
  for (const [note, orig] of moveSnapshot) {
    note.time = Math.max(0, orig.time + dSec)
    note.midi = Math.max(0, Math.min(127, orig.midi + dMidi))
  }
  redraw()
}
function onMoveUp() {
  window.removeEventListener('mousemove', onMoveMove); window.removeEventListener('mouseup', onMoveUp)
  moveSnapshot = null
  if (moved) { commit() }
  else if (collapseOnClick) { selectOnly(collapseOnClick); redraw() }
  collapseOnClick = null
}

// Marquee
function onMarqueeMove(e: MouseEvent) {
  if (!marquee.value) return
  const pt = pointerBufferXY(e); if (!pt) return
  marquee.value = { ...marquee.value, x1: pt.px, y1: pt.py }
  redraw()
}
function onMarqueeUp() {
  window.removeEventListener('mousemove', onMarqueeMove); window.removeEventListener('mouseup', onMarqueeUp)
  const m = marquee.value; marquee.value = null
  if (!m) return
  const mx = Math.min(m.x0, m.x1), my = Math.min(m.y0, m.y1)
  const mw = Math.abs(m.x1 - m.x0), mh = Math.abs(m.y1 - m.y0)
  const vp = viewport()
  const s = new Set(selected.value)   // shift-drag extends; plain-drag already cleared on mousedown
  for (const note of localNotes.value) {
    const r = noteRectZoom(note, vp)
    if (rectsOverlap(mx, my, Math.max(1, mw), Math.max(1, mh), r.x, r.y, r.w, r.h)) s.add(note)
  }
  selected.value = s
  redraw()   // selection change only — not a note edit, so no dirty
}

// Velocity
function applyVelocity(px: number, py: number) {
  const v = velocityFromLaneY(py, veloTop(), VELO_H)
  if (veloTargets) {
    for (const n of veloTargets) n.velocity = v
  } else {
    const note = noteAtX(px)
    if (note) note.velocity = v
  }
}
function onVeloMove(e: MouseEvent) {
  const pt = pointerBufferXY(e); if (!pt) return
  applyVelocity(pt.px, pt.py)
  redraw()
}
function onVeloUp() {
  window.removeEventListener('mousemove', onVeloMove); window.removeEventListener('mouseup', onVeloUp)
  veloTargets = null
  commit()
}

// Scrollbars
function onSbMove(e: MouseEvent) {
  const pt = pointerBufferXY(e); if (!pt) return
  const { gw, gh } = gridSize()
  if (sbDrag === 'h') {
    const thumbW = Math.max(24, (gw / contentW.value) * gw)
    scrollX.value = ((pt.px - GUTTER_W - thumbW / 2) / Math.max(1, gw - thumbW)) * (contentW.value - gw)
  } else if (sbDrag === 'v') {
    const thumbH = Math.max(24, (gh / contentH.value) * gh)
    scrollY.value = ((pt.py - RULER_H - thumbH / 2) / Math.max(1, gh - thumbH)) * (contentH.value - gh)
  }
  redraw()
}
function onSbUp() {
  window.removeEventListener('mousemove', onSbMove); window.removeEventListener('mouseup', onSbUp)
  sbDrag = null
}

function onHover(e: MouseEvent) {
  const el = canvasEl.value
  if (!el || draftNote.value || resizing || marquee.value) return
  const pt = pointerBufferXY(e)
  if (!pt || !inGrid(pt.px, pt.py)) { el.style.cursor = ''; return }
  let onEdge = false
  const hit = hitTest(pt.px, pt.py)
  if (hit !== null && !isDrumPart.value) {
    const r = noteRectZoom(localNotes.value[hit], viewport())
    onEdge = nearRightEdge(pt.px, r.x, r.w)
  }
  el.style.cursor = onEdge ? 'ew-resize' : (hit !== null ? 'move' : (tool.value === 'select' ? 'crosshair' : 'cell'))
}

function onWheel(e: WheelEvent) {
  if (e.ctrlKey || e.metaKey) {
    const pt = pointerBufferXY(e); e.preventDefault()
    const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12
    const beatUnderCursor = pt ? (pt.px - GUTTER_W + scrollX.value) / pxPerBeat.value : 0
    pxPerBeat.value = Math.max(MIN_PXB, Math.min(MAX_PXB, pxPerBeat.value * factor))
    if (pt) scrollX.value = beatUnderCursor * pxPerBeat.value - (pt.px - GUTTER_W)
    redraw(); return
  }
  e.preventDefault()
  if (e.shiftKey) scrollX.value += e.deltaY + e.deltaX
  else { scrollX.value += e.deltaX; scrollY.value += e.deltaY }
  redraw()
}

function onKeyDown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    if (selected.value.size > 0) { selected.value = new Set(); e.preventDefault(); redraw(); return }
    emit('close'); return
  }
  if (e.key === 'a' && (e.ctrlKey || e.metaKey)) {
    selected.value = new Set(localNotes.value); e.preventDefault(); redraw(); return
  }
  if (selected.value.size === 0) return
  const sel = [...selected.value]
  if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
    if (isDrumPart.value) return
    const step = (e.shiftKey ? 12 : 1) * (e.key === 'ArrowUp' ? 1 : -1)
    for (const n of sel) n.midi = Math.max(0, Math.min(127, n.midi + step))
  } else if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
    const step = (e.shiftKey ? BEATS_PER_BAR : division.value) * secPerBeat.value * (e.key === 'ArrowRight' ? 1 : -1)
    for (const n of sel) n.time = Math.max(0, n.time + step)
  } else if (e.key === 'Delete' || e.key === 'Backspace') {
    localNotes.value = localNotes.value.filter(n => !selected.value.has(n))
    selected.value = new Set()
  } else {
    return
  }
  e.preventDefault()
  commit()
}

function commit() {
  dirty.value = true
  emit('notes-changed', localNotes.value.map(x => ({ ...x })), true)
  redraw()
}

// ── Playback + audition ──────────────────────────────────────────────────────
function audition(midi: number) {
  player.audition(props.styleId, partForAudio.value, midi)
}

/** Encode the live edit buffer into a one-track MIDI blob on the part's channel, so
 *  the shared player renders it with the correct instrument (unsaved edits included). */
function buildPartMidi(): string {
  const midi = new Midi()
  midi.header.setTempo(60 / secPerBeat.value)
  const track = midi.addTrack()
  track.channel = partChannel.value
  // Bass (channel 1) is monophonic; every other part is polyphonic. Sanitizing avoids
  // Tone's "start time must be strictly greater" error when edits stack notes.
  const safe = sanitizeNotesForPlayback(localNotes.value, partChannel.value === 1)
  for (const n of safe) {
    track.addNote({ midi: Math.round(n.midi), time: n.time, duration: Math.max(0.02, n.duration), velocity: n.velocity })
  }
  if (blobUrl) URL.revokeObjectURL(blobUrl)
  blobUrl = URL.createObjectURL(new Blob([midi.toArray() as BlobPart], { type: 'audio/midi' }))
  return blobUrl
}

function loopRegionSec(): { start: number; end: number } | undefined {
  if (loopStartBeat.value === null || loopEndBeat.value === null) return undefined
  const a = Math.min(loopStartBeat.value, loopEndBeat.value) * secPerBeat.value
  const b = Math.max(loopStartBeat.value, loopEndBeat.value) * secPerBeat.value
  return b > a ? { start: a, end: b } : undefined
}

async function togglePlay() {
  if (playing.value) { stopPlayback(); return }
  const url = buildPartMidi()
  playing.value = true
  await player.toggle(url, props.styleId, `Edit: ${props.partName}`, false, loopRegionSec())
  startPlayhead()
}

function stopPlayback() {
  player.stop()
  playing.value = false
  stopPlayhead()
  playheadSec.value = 0
  redraw()
}

function startPlayhead() {
  stopPlayhead()
  const tick = () => {
    playheadSec.value = Tone.getTransport().seconds
    // The player stops itself at the end of a non-looping part; reflect that here.
    if (blobUrl && !player.isPlayingUrl(blobUrl)) { playing.value = false; stopPlayhead(); redraw(); return }
    redraw()
    phRaf = requestAnimationFrame(tick)
  }
  phRaf = requestAnimationFrame(tick)
}
function stopPlayhead() {
  if (phRaf !== null) { cancelAnimationFrame(phRaf); phRaf = null }
}

function clearLoop() {
  loopStartBeat.value = null
  loopEndBeat.value = null
  if (playing.value) Tone.getTransport().loop = false
  redraw()
}

/** Apply the current loop region to a running transport (live retune while playing). */
function syncLoopToTransport() {
  const r = loopRegionSec()
  if (!playing.value) return
  if (r) {
    Tone.getTransport().loop = true
    Tone.getTransport().loopStart = r.start
    Tone.getTransport().loopEnd = r.end
  } else {
    Tone.getTransport().loop = false
  }
}

// ── Zoom controls ──────────────────────────────────────────────────────────
function zoomH(factor: number) {
  const { gw } = gridSize()
  const centerBeat = (scrollX.value + gw / 2) / pxPerBeat.value
  pxPerBeat.value = Math.max(MIN_PXB, Math.min(MAX_PXB, pxPerBeat.value * factor))
  scrollX.value = centerBeat * pxPerBeat.value - gw / 2
  redraw()
}
function zoomV(factor: number) {
  const { gh } = gridSize()
  const centerSemis = (scrollY.value + gh / 2) / pxPerSemitone.value
  pxPerSemitone.value = Math.max(MIN_PXS, Math.min(MAX_PXS, pxPerSemitone.value * factor))
  scrollY.value = centerSemis * pxPerSemitone.value - gh / 2
  redraw()
}
function fit() {
  const { gw, gh } = gridSize()
  pxPerBeat.value = Math.max(MIN_PXB, Math.min(MAX_PXB, gw / totalBeats.value))
  pxPerSemitone.value = Math.max(MIN_PXS, Math.min(MAX_PXS, gh / pitchCount.value))
  scrollX.value = 0; scrollY.value = 0
  redraw()
}

function markSaved() {
  dirty.value = false
  emit('notes-changed', localNotes.value.map(x => ({ ...x })), false)
}
defineExpose({ markSaved })

// ── Lifecycle ────────────────────────────────────────────────────────────────
function syncCanvasSize() {
  const el = canvasEl.value, vp = viewportEl.value
  if (!el || !vp) return
  const rect = vp.getBoundingClientRect()
  const w = Math.round(rect.width), h = Math.round(rect.height)
  if (w > 0 && h > 0 && (el.width !== w || el.height !== h)) { el.width = w; el.height = h; redraw() }
}

watch(() => props.notes, (n) => {
  localNotes.value = n.map(x => ({ ...x }))
  selected.value = new Set()
  dirty.value = false
  redraw()
})
watch([division, tool, theme], () => redraw())

onMounted(async () => {
  await nextTick()
  syncCanvasSize()
  fit()
  canvasEl.value?.focus()
  player.prepareAudition(props.styleId, partForAudio.value)   // warm the preview instrument
  ro = new ResizeObserver(syncCanvasSize)
  if (viewportEl.value) ro.observe(viewportEl.value)
})

onUnmounted(() => {
  ro?.disconnect()
  if (playing.value) player.stop()
  stopPlayhead()
  if (blobUrl) { URL.revokeObjectURL(blobUrl); blobUrl = null }
  for (const [ev, fn] of [
    ['mousemove', onInsertMove], ['mouseup', onInsertUp],
    ['mousemove', onResizeMove], ['mouseup', onResizeUp],
    ['mousemove', onMoveMove], ['mouseup', onMoveUp],
    ['mousemove', onMarqueeMove], ['mouseup', onMarqueeUp],
    ['mousemove', onVeloMove], ['mouseup', onVeloUp],
    ['mousemove', onSbMove], ['mouseup', onSbUp],
    ['mousemove', onLoopMove], ['mouseup', onLoopUp],
  ] as [string, EventListener][]) window.removeEventListener(ev, fn)
})
</script>

<style scoped>
.pre-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.72);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 250;
}
.pre-modal {
  background: var(--panel);
  border: 1px solid color-mix(in srgb, var(--accent) 33%, transparent);
  border-radius: 12px;
  width: min(1100px, 96vw);
  height: min(760px, 88vh);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.pre-header {
  display: flex; align-items: center; gap: 0.75rem;
  padding: 0.7rem 1rem; border-bottom: 1px solid var(--surface); flex-shrink: 0;
}
.pre-title { font-size: 0.9rem; font-weight: 600; color: var(--text); }
.pre-part { color: var(--accent); text-transform: capitalize; }
.pre-meta { font-size: var(--t-meta); color: var(--text-dim); flex: 1; }
.pre-x {
  background: none; border: none; color: var(--text-dim);
  font-size: 1rem; cursor: pointer; padding: 0.2rem 0.4rem; border-radius: var(--r-sm);
}
.pre-x:hover { color: var(--text); background: var(--surface-hover); }

.pre-toolbar {
  display: flex; align-items: center; gap: 0.6rem;
  padding: 0.5rem 1rem; border-bottom: 1px solid var(--surface); flex-shrink: 0; flex-wrap: wrap;
}
.pre-group { display: flex; align-items: center; gap: 0.25rem; }
.pre-glabel {
  font-size: var(--t-micro); text-transform: uppercase; letter-spacing: 0.06em;
  color: var(--text-faint); margin-right: 0.15rem;
}
.pre-axis { font-size: 0.85rem; color: var(--text-dim); margin: 0 0.05rem 0 0.2rem; }
.pre-btn {
  height: 28px; min-width: 28px;
  background: transparent; border: 1px solid var(--line); border-radius: var(--r-sm);
  color: var(--ink-dim); font-size: var(--t-meta); cursor: pointer; padding: 0 0.5rem;
  transition: background 0.14s, color 0.14s, border-color 0.14s;
}
.pre-btn:hover:not(:disabled) { border-color: var(--ink-faint); color: var(--ink); }
.pre-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.pre-tool.active { border-color: var(--accent-edge); background: var(--accent-wash); color: var(--accent); }
.pre-fit { font-weight: 600; }
.pre-play { font-size: 0.9rem; color: var(--accent); border-color: var(--accent-edge); }
.pre-play:hover:not(:disabled) { background: var(--accent-wash); }
.pre-loopclear { color: var(--good); border-color: color-mix(in srgb, var(--good) 40%, var(--line)); }
.pre-snap { font-size: var(--t-meta); color: var(--text-dim); display: flex; align-items: center; gap: 0.35rem; }
.pre-snap select { height: 28px; }
.pre-selcount {
  font-size: var(--t-meta); color: var(--accent);
  background: var(--accent-wash); border: 1px solid var(--accent-edge);
  border-radius: var(--r-sm); padding: 0.1rem 0.45rem;
}
.pre-spacer-flex { flex: 1; }
.pre-save { border-color: var(--accent-edge); background: var(--accent-wash); color: var(--accent); font-weight: 600; }
.pre-save:disabled { background: transparent; }

.pre-viewport { flex: 1; min-height: 0; position: relative; overflow: hidden; }
.pre-canvas { display: block; width: 100%; height: 100%; outline: none; }

.pre-hint {
  flex-shrink: 0; padding: 0.4rem 1rem; border-top: 1px solid var(--surface);
  font-size: var(--t-micro); color: var(--text-faint);
}
</style>
