<template>
  <canvas ref="canvasEl" class="piano-roll" />
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import * as Tone from 'tone'
import type { ParsedNote } from '../composables/useMidiPlayer'

const props = defineProps<{
  notes: ParsedNote[]
  duration: number
  playing: boolean
}>()

const canvasEl = ref<HTMLCanvasElement | null>(null)
let rafId: number | null = null
let ro: ResizeObserver | null = null

// Pitch range of melodic notes (with a little padding)
function getPitchRange() {
  const melodic = props.notes.filter(n => !n.isPercussion)
  if (melodic.length === 0) return { min: 48, max: 84 }
  const min = Math.min(...melodic.map(n => n.midi))
  const max = Math.max(...melodic.map(n => n.midi))
  const pad = Math.max(2, Math.round((max - min) * 0.1))
  return { min: min - pad, max: max + pad }
}

function draw(playheadTime = 0) {
  const el = canvasEl.value
  if (!el) return
  const ctx = el.getContext('2d')
  if (!ctx) return

  const w = el.width
  const h = el.height
  const dur = props.duration || 1
  const { min: minP, max: maxP } = getPitchRange()
  const pitchRange = maxP - minP || 1

  // Background
  ctx.fillStyle = '#020608'
  ctx.fillRect(0, 0, w, h)

  // Subtle horizontal pitch lines
  ctx.strokeStyle = '#051015'
  ctx.lineWidth = 1
  for (let p = minP; p <= maxP; p++) {
    const y = h - ((p - minP) / pitchRange) * h
    ctx.beginPath()
    ctx.moveTo(0, y)
    ctx.lineTo(w, y)
    ctx.stroke()
  }

  const noteH = Math.max(2, (h / pitchRange) * 0.85)

  for (const note of props.notes) {
    const x = (note.time / dur) * w
    const noteW = Math.max(2, (note.duration / dur) * w - 1)
    const alpha = 0.45 + note.velocity * 0.55

    if (note.isPercussion) {
      // Drum hits: short vertical tick at the bottom
      ctx.fillStyle = `rgba(251, 191, 36, ${alpha})`
      ctx.fillRect(x, h - 6, Math.max(2, noteW * 0.3), 6)
    } else {
      const y = h - ((note.midi - minP + 1) / pitchRange) * h
      ctx.fillStyle = `rgba(0, 200, 255, ${alpha})`
      ctx.fillRect(x, y, noteW, noteH)
    }
  }

  // Playhead
  if (props.playing || playheadTime > 0) {
    const px = Math.min(w - 1, (playheadTime / dur) * w)
    // Glow effect
    const grad = ctx.createLinearGradient(px - 4, 0, px + 4, 0)
    grad.addColorStop(0, 'rgba(255,255,255,0)')
    grad.addColorStop(0.5, 'rgba(255,255,255,0.7)')
    grad.addColorStop(1, 'rgba(255,255,255,0)')
    ctx.fillStyle = grad
    ctx.fillRect(px - 4, 0, 8, h)
  }
}

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
  if (isPlaying) {
    startRaf()
  } else {
    stopRaf()
    draw(0)
  }
})

watch(() => props.notes, () => draw(0))

onMounted(() => {
  syncCanvasSize()
  draw(0)
  ro = new ResizeObserver(syncCanvasSize)
  if (canvasEl.value) ro.observe(canvasEl.value)
})

onUnmounted(() => {
  stopRaf()
  ro?.disconnect()
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
</style>
