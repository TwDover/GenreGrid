<template>
  <div class="quality-panel">
    <div class="quality-header">
      <span class="quality-label">Quality</span>
      <span class="quality-badge" :class="labelClass">{{ score.label }}</span>
      <span class="quality-total">{{ pct(score.total) }}%</span>
    </div>
    <div class="quality-bars">
      <div v-for="dim in dimensions" :key="dim.key" class="dim-row">
        <span class="dim-name">{{ dim.label }}</span>
        <div class="dim-bar-track">
          <div class="dim-bar-fill" :style="{ width: pct(score[dim.key]) + '%', background: barColor(score[dim.key]) }"></div>
        </div>
        <span class="dim-value">{{ pct(score[dim.key]) }}</span>
      </div>
    </div>
    <ul v-if="score.flags.length" class="quality-flags">
      <li v-for="flag in score.flags" :key="flag">{{ flag }}</li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { QualityScore } from '../types/midi'

const props = defineProps<{ score: QualityScore }>()

const dimensions = [
  { key: 'harmonic' as const, label: 'Harmonic' },
  { key: 'rhythm'   as const, label: 'Rhythm'   },
  { key: 'register' as const, label: 'Register' },
  { key: 'density'  as const, label: 'Density'  },
  { key: 'mix'      as const, label: 'Mix'       },
]

const labelClass = computed(() => ({
  'label-excellent': props.score.label === 'Excellent',
  'label-good':      props.score.label === 'Good',
  'label-fair':      props.score.label === 'Fair',
  'label-weak':      props.score.label === 'Weak',
}))

function pct(v: number): number {
  return Math.round(v * 100)
}

function barColor(v: number): string {
  if (v >= 0.82) return '#34d399'   // green
  if (v >= 0.68) return '#60a5fa'   // blue
  if (v >= 0.52) return '#fbbf24'   // amber
  return '#f87171'                   // red
}
</script>

<style scoped>
.quality-panel {
  padding: 0.6rem 0.75rem;
  background: #12121a;
  border-radius: 6px;
  border: 1px solid #2a2a3e;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.quality-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.quality-label {
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #55556a;
}

.quality-badge {
  font-size: 0.72rem;
  font-weight: 700;
  padding: 0.1rem 0.5rem;
  border-radius: 10px;
  letter-spacing: 0.04em;
}

.label-excellent { background: #064e3b; color: #34d399; }
.label-good      { background: #1e3a5f; color: #60a5fa; }
.label-fair      { background: #451a03; color: #fbbf24; }
.label-weak      { background: #3b0f0f; color: #f87171; }

.quality-total {
  font-size: 0.82rem;
  font-family: monospace;
  color: #a78bfa;
  margin-left: auto;
}

.quality-bars {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.dim-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.dim-name {
  font-size: 0.7rem;
  color: #8888a0;
  width: 52px;
  flex-shrink: 0;
}

.dim-bar-track {
  flex: 1;
  height: 4px;
  background: #2a2a3e;
  border-radius: 2px;
  overflow: hidden;
}

.dim-bar-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.4s ease;
}

.dim-value {
  font-size: 0.68rem;
  font-family: monospace;
  color: #55556a;
  width: 24px;
  text-align: right;
}

.quality-flags {
  margin: 0;
  padding: 0 0 0 0.8rem;
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}

.quality-flags li {
  font-size: 0.7rem;
  color: #fbbf24;
  list-style: disc;
}
</style>
