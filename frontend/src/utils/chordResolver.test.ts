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
import { resolveProgression, scaleNotes } from './chordResolver'

describe('resolveProgression', () => {
  it('resolves a major pop progression to concrete chords', () => {
    expect(resolveProgression(['I', 'V', 'vi', 'IV'], 'C', 'major')).toEqual(['C', 'G', 'Am', 'F'])
  })

  it('resolves a minor progression', () => {
    expect(resolveProgression(['i', 'VI', 'III', 'VII'], 'A', 'minor')).toEqual(['Am', 'F', 'C', 'G'])
  })

  it('carries chord extensions and quality', () => {
    const [ii, V, I] = resolveProgression(['ii7', 'V7', 'Imaj7'], 'C', 'major')
    expect(ii).toBe('Dm7')
    expect(V).toBe('G7')
    expect(I).toBe('Cmaj7')
  })

  it('passes through unknown symbols unchanged', () => {
    expect(resolveProgression(['???'], 'C', 'major')).toEqual(['???'])
  })
})

describe('scaleNotes', () => {
  it('returns the 7 pitch classes of C major', () => {
    const s = scaleNotes('C', 'major')
    expect([...s].sort((a, b) => a - b)).toEqual([0, 2, 4, 5, 7, 9, 11])
  })
})
