/*
 * GenreGrid — a style-based MIDI generator.
 * Copyright (C) 2026 Tw Dover
 *
 * This program is free software: you can redistribute it and/or modify it under
 * the terms of the GNU General Public License as published by the Free Software
 * Foundation, either version 3 of the License, or (at your option) any later
 * version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
 * <https://www.gnu.org/licenses/> for details.
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import QualityBadge from './QualityBadge.vue'
import type { QualityScore } from '../types/midi'

const score: QualityScore = {
  total: 0.9, harmonic: 0.95, separation: 0.8, rhythm: 0.88,
  contour: 0.7, density: 0.85, mix: 0.82, label: 'Excellent',
  flags: ['Melody clashes heavily with chords — many non-scale tones'],
}

describe('QualityBadge', () => {
  it('renders the label, total, dimensions and flags', () => {
    const wrapper = mount(QualityBadge, { props: { score } })
    const text = wrapper.text()
    expect(text).toContain('Excellent')
    expect(text).toContain('90%')                 // total
    // every dimension label is shown
    for (const label of ['Harmonic', 'Rhythm', 'Register', 'Contour', 'Density', 'Mix']) {
      expect(text).toContain(label)
    }
    // the flag is listed
    expect(text).toContain('Melody clashes heavily with chords')
  })

  it('renders a bar per dimension', () => {
    const wrapper = mount(QualityBadge, { props: { score } })
    expect(wrapper.findAll('.dim-row')).toHaveLength(6)
  })
})
