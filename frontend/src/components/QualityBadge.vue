<!--
  GenreGrid — a style-based MIDI generator.
  Copyright (C) 2026 Tw Dover

  This program is free software: you can redistribute it and/or modify it under
  the terms of the GNU General Public License v3 or (at your option) any later
  version. Distributed WITHOUT ANY WARRANTY. See <https://www.gnu.org/licenses/>.
-->
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
          <div class="dim-bar-fill" :style="{ width: pct(score[dim.key] ?? 0) + '%', background: barColor(score[dim.key] ?? 0) }"></div>
        </div>
        <span class="dim-value">{{ pct(score[dim.key] ?? 0) }}</span>
      </div>
    </div>
    <ul v-if="score.flags.length" class="quality-flags">
      <li v-for="flag in score.flags" :key="flag" :title="FLAG_TIPS[flag] ?? ''" class="flag-item">
        {{ flag }}
        <span v-if="FLAG_TIPS[flag]" class="flag-tip">{{ FLAG_TIPS[flag] }}</span>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { QualityScore } from '../types/midi'

const props = defineProps<{ score: QualityScore }>()

const FLAG_TIPS: Record<string, string> = {
  'Melody clashes heavily with chords — many non-scale tones': 'Try a simpler scale (pentatonic minor) or lower complexity.',
  'Melody has notable dissonance against chord tones': 'Reduce complexity or switch to a scale that fits the style.',
  'Melody sits below chord voicings — register overlap': 'This style may have high chord registers. Try a different key.',
  'Melody and chords are too close in register': 'Try enabling arpeggio instead of melody, or increase bars.',
  'Chords and bass are in the same register': 'This is usually fixed automatically on retry — try generating again.',
  'Kick pattern diverges from style signature': 'The drums drifted from the style. Try regenerating just the drums.',
  "Chord rhythm doesn't match style comping pattern": 'Try regenerating just the chords part.',
  'Melody is much sparser than expected for this style': 'Increase complexity or bars.',
  'Melody is much denser than expected for this style': 'Decrease complexity or increase bars.',
  'Bass is much sparser than expected': 'Try regenerating just the bass.',
  'Bass is much denser than expected': 'Normal for styles with call-response bass fills.',
  'Chords overpower melody — mix sounds cluttered': 'This mix issue usually resolves on retry.',
  'Melody velocity is too dominant': 'This resolves on retry.',
  'Bass is very quiet relative to chords': 'Try regenerating just the bass.',
  'Bass overpowers the mid-range': 'Normal for 808-heavy styles like trap and drill.',
}

type DimKey = 'harmonic' | 'rhythm' | 'separation' | 'contour' | 'density' | 'mix' | 'style_match'
const dimensions = computed<{ key: DimKey; label: string }[]>(() => {
  const dims: { key: DimKey; label: string }[] = [
    { key: 'harmonic', label: 'Harmonic' },
    { key: 'rhythm', label: 'Rhythm' },
    { key: 'separation', label: 'Register' },
    { key: 'contour', label: 'Contour' },
    { key: 'density', label: 'Density' },
    { key: 'mix', label: 'Mix' },
  ]
  // "Style" only when a corpus prior scored it (genre-match dimension).
  if ((props.score.style_match ?? 0) > 0) dims.push({ key: 'style_match', label: 'Style' })
  return dims
})

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
  if (v >= 0.68) return '#00c8ff'   // cyan
  if (v >= 0.52) return '#fbbf24'   // amber
  return '#f87171'                   // red
}
</script>

<style scoped>
.quality-panel {
  padding: 0.6rem 0.75rem;
  background: #040a0e;
  border-radius: 6px;
  border: 1px solid #0d2535;
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
  color: #2a4550;
}

.quality-badge {
  font-size: 0.72rem;
  font-weight: 700;
  padding: 0.1rem 0.5rem;
  border-radius: 10px;
  letter-spacing: 0.04em;
}

.label-excellent { background: #064e3b; color: #34d399; }
.label-good      { background: #001e35; color: #00c8ff; }
.label-fair      { background: #451a03; color: #fbbf24; }
.label-weak      { background: #3b0f0f; color: #f87171; }

.quality-total {
  font-size: 0.82rem;
  font-family: monospace;
  color: #00c8ff;
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
  color: #4a7080;
  width: 52px;
  flex-shrink: 0;
}

.dim-bar-track {
  flex: 1;
  height: 4px;
  background: #0d2535;
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
  color: #2a4550;
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

.flag-item {
  cursor: default;
}
.flag-tip {
  display: block;
  font-size: 0.65rem;
  color: #2a4550;
  margin-top: 0.1rem;
  font-style: italic;
}
</style>
