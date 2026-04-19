<template>
  <svg viewBox="0 0 120 120" width="120" height="120" xmlns="http://www.w3.org/2000/svg">
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
    <!-- Dots -->
    <circle
      v-for="(m, i) in metrics"
      :key="`dot-${i}`"
      :cx="cx(i, m.value)" :cy="cy(i, m.value)"
      r="2.5"
      fill="#00c8ff"
    />
    <!-- Labels -->
    <text
      v-for="(m, i) in metrics"
      :key="`lbl-${i}`"
      :x="cx(i, 1.15)" :y="cy(i, 1.15)"
      text-anchor="middle"
      dominant-baseline="middle"
      font-size="7"
      fill="#4a7080"
    >{{ m.label }}</text>
  </svg>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ style: Record<string, any> }>()

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
</script>
