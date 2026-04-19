<template>
  <svg
    viewBox="0 0 120 120"
    :width="size" :height="size"
    xmlns="http://www.w3.org/2000/svg"
    :style="editable ? 'cursor: default; user-select: none' : ''"
    @pointermove.passive="onPointerMove"
    @pointerup="onPointerUp"
    @pointercancel="onPointerUp"
  >
    <!-- Background web rings -->
    <polygon
      v-for="ring in [0.33, 0.66, 1.0]"
      :key="ring"
      :points="hexPoints(ring)"
      fill="none"
      stroke="#0d2535"
      stroke-width="1"
    />
    <!-- Axes -->
    <line
      v-for="(_, i) in metrics"
      :key="`axis-${i}`"
      x1="60" y1="60"
      :x2="cx(i, 1.0)" :y2="cy(i, 1.0)"
      stroke="#0d2535"
      stroke-width="1"
    />
    <!-- Data polygon -->
    <polygon
      :points="dataPoints"
      fill="#00c8ff22"
      stroke="#00c8ff"
      stroke-width="1.5"
    />
    <!-- Dots (draggable when editable) -->
    <circle
      v-for="(m, i) in metrics"
      :key="`dot-${i}`"
      :cx="cx(i, m.value)" :cy="cy(i, m.value)"
      :r="editable ? 4 : 2.5"
      fill="#00c8ff"
      :style="editable ? 'cursor: grab' : ''"
      @pointerdown.stop.prevent="editable && onPointerDown($event, i)"
    />
    <!-- Labels -->
    <text
      v-for="(m, i) in metrics"
      :key="`lbl-${i}`"
      :x="cx(i, 1.22)" :y="cy(i, 1.22)"
      text-anchor="middle"
      dominant-baseline="middle"
      font-size="7"
      :fill="draggingIdx === i ? '#00c8ff' : '#4a7080'"
    >{{ m.label }}</text>
  </svg>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

const props = defineProps<{
  style: Record<string, any>
  size?: number
  editable?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:style', style: Record<string, any>): void
}>()

const size = computed(() => props.size ?? 120)

const RADIUS = 45
const CENTER = 60
const N = 6

const metrics = computed(() => [
  { label: 'Swing',  value: Math.max(0, Math.min(1, ((props.style.drums?.swing ?? 0.5) - 0.5) / 0.25)) },
  { label: 'Hats',   value: props.style.drums?.hat_density ?? 0.5 },
  { label: 'Melody', value: props.style.melody?.density ?? 0.5 },
  { label: 'Bass',   value: props.style.bass?.pattern_density ?? 0.5 },
  { label: '7ths',   value: props.style.chord_extensions?.allow_7th ?? 0.5 },
  { label: 'Groove', value: Math.max(0, Math.min(1, 0.5 + (props.style.groove_push ?? 0) * 10)) },
])

function angle(i: number): number {
  return -Math.PI / 2 + (2 * Math.PI / N) * i
}

function cx(i: number, r: number): number {
  return CENTER + Math.cos(angle(i)) * RADIUS * r
}

function cy(i: number, r: number): number {
  return CENTER + Math.sin(angle(i)) * RADIUS * r
}

function hexPoints(r: number): string {
  return Array.from({ length: N }, (_, i) => `${cx(i, r)},${cy(i, r)}`).join(' ')
}

const dataPoints = computed(() =>
  metrics.value.map((m, i) => `${cx(i, m.value)},${cy(i, m.value)}`).join(' ')
)

// ── Drag interaction ──────────────────────────────────────────────────────────

const draggingIdx = ref(-1)

// Map each metric index to a setter that writes into a style clone
const SETTERS: Array<(s: Record<string, any>, v: number) => void> = [
  (s, v) => { s.drums = { ...s.drums, swing: 0.5 + v * 0.25 } },
  (s, v) => { s.drums = { ...s.drums, hat_density: v } },
  (s, v) => { s.melody = { ...s.melody, density: v } },
  (s, v) => { s.bass = { ...s.bass, pattern_density: v } },
  (s, v) => { s.chord_extensions = { ...s.chord_extensions, allow_7th: v } },
  (s, v) => { s.groove_push = (v - 0.5) / 10 },
]

function onPointerDown(evt: PointerEvent, i: number) {
  draggingIdx.value = i
  ;(evt.target as SVGElement).setPointerCapture(evt.pointerId)
}

function onPointerMove(evt: PointerEvent) {
  if (draggingIdx.value < 0) return
  const svg = evt.currentTarget as SVGSVGElement
  const rect = svg.getBoundingClientRect()
  // Map from screen pixels to viewBox coordinates (viewBox = 0 0 120 120)
  const vx = ((evt.clientX - rect.left) / rect.width) * 120 - CENTER
  const vy = ((evt.clientY - rect.top) / rect.height) * 120 - CENTER
  const theta = angle(draggingIdx.value)
  const projected = vx * Math.cos(theta) + vy * Math.sin(theta)
  const raw = Math.max(0, Math.min(1, projected / RADIUS))
  const clone = JSON.parse(JSON.stringify(props.style))
  SETTERS[draggingIdx.value]?.(clone, raw)
  emit('update:style', clone)
}

function onPointerUp() {
  draggingIdx.value = -1
}
</script>
