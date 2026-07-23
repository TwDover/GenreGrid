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
import {
  isAudioFile,
  parseSampleName,
  buildManifest,
  resolvePartInstrument,
  type InstrumentAssignments,
} from './customInstruments'

describe('isAudioFile', () => {
  it('accepts common audio extensions, rejects others', () => {
    for (const f of ['a.mp3', 'a.WAV', 'a.ogg', 'a.flac', 'a.m4a']) expect(isAudioFile(f)).toBe(true)
    for (const f of ['a.txt', 'a.json', 'a.png', 'velocity.json', 'a']) expect(isAudioFile(f)).toBe(false)
  })
})

describe('parseSampleName', () => {
  it('reads plain note names and normalises sharps', () => {
    expect(parseSampleName('C4.mp3').note).toBe('C4')
    expect(parseSampleName('A4.wav').note).toBe('A4')
    expect(parseSampleName('F#3.ogg').note).toBe('F#3')
    expect(parseSampleName('As3.mp3').note).toBe('A#3')   // 's' → '#'
    expect(parseSampleName('Gb2.mp3').note).toBe('Gb2')   // flat preserved
  })

  it('ignores a name prefix and takes the trailing note', () => {
    expect(parseSampleName('Piano_C4.mp3').note).toBe('C4')
    expect(parseSampleName('MyRhodes-A3.wav').note).toBe('A3')
  })

  it('does not false-match letters glued to digits', () => {
    expect(parseSampleName('Bass1.wav').note).toBeNull()
    expect(parseSampleName('kick.wav').note).toBeNull()
  })

  it('reads a velocity-layer hint from the folder or a suffix', () => {
    expect(parseSampleName('hard/C4.mp3').layer).toBe('hard')
    expect(parseSampleName('soft/C4.mp3').layer).toBe('soft')
    expect(parseSampleName('Vibes_C4_v2.mp3').layer).toBe('v2')
    expect(parseSampleName('C4.mp3').layer).toBeNull()
  })

  it('reads a round-robin index', () => {
    expect(parseSampleName('C4_rr1.mp3').rr).toBe(1)
    expect(parseSampleName('C4_rr2.mp3').rr).toBe(2)
    expect(parseSampleName('C4.mp3').rr).toBeNull()
  })
})

describe('buildManifest', () => {
  it('T1: a single un-pitched file becomes a one-shot at the default root', () => {
    const { manifest, mapped, skipped } = buildManifest(['MySound.wav'])
    expect(mapped).toBe(1)
    expect(skipped).toEqual([])
    expect(manifest.layers).toHaveLength(1)
    expect(manifest.layers[0]).toEqual({ maxVelocity: 1, urls: { C4: 'MySound.wav' } })
  })

  it('skips non-audio files', () => {
    const { skipped, mapped } = buildManifest(['C4.mp3', 'readme.txt', 'cover.png'])
    expect(skipped).toEqual(['readme.txt', 'cover.png'])
    expect(mapped).toBe(1)
  })

  it('T2: note-named files become one full-range layer, one zone per note', () => {
    const { manifest } = buildManifest(['C4.mp3', 'E4.mp3', 'G4.mp3'])
    expect(manifest.layers).toHaveLength(1)
    expect(manifest.layers[0].maxVelocity).toBe(1)
    expect(manifest.layers[0].urls).toEqual({ C4: 'C4.mp3', E4: 'E4.mp3', G4: 'G4.mp3' })
  })

  it('T3: velocity folders become ascending layers, top ceiling forced to 1', () => {
    const { manifest } = buildManifest(['soft/C4.mp3', 'hard/C4.mp3', 'soft/E4.mp3', 'hard/E4.mp3'])
    expect(manifest.layers).toHaveLength(2)
    // soft ranks below hard, so layer 0 is soft with a fractional ceiling, layer 1 hard=1.
    expect(manifest.layers[0].urls.C4).toBe('soft/C4.mp3')
    expect(manifest.layers[0].maxVelocity).toBeCloseTo(0.5)
    expect(manifest.layers[1].urls.C4).toBe('hard/C4.mp3')
    expect(manifest.layers[1].maxVelocity).toBe(1)
  })

  it('T3: repeated note+layer files become round-robins, ordered by rr index', () => {
    const { manifest } = buildManifest(['C4_rr2.mp3', 'C4_rr1.mp3'])
    expect(manifest.layers[0].urls.C4).toEqual(['C4_rr1.mp3', 'C4_rr2.mp3'])
  })

  it('empty / all-skipped input yields no layers', () => {
    expect(buildManifest(['notes.txt']).manifest.layers).toEqual([])
  })
})

describe('resolvePartInstrument', () => {
  const assignments: InstrumentAssignments = {
    defaults: { bass: 'inst-bass', chords: 'inst-rhodes' },
    perStyle: { jazz: { chords: 'inst-jazzpiano' } },
  }

  it('per-style override wins over the global default', () => {
    expect(resolvePartInstrument(assignments, 'jazz', 'chords', 'electric_piano_1'))
      .toEqual({ source: 'custom', id: 'inst-jazzpiano' })
  })

  it('falls back to the global default when no per-style override', () => {
    expect(resolvePartInstrument(assignments, 'soul', 'chords', 'electric_piano_1'))
      .toEqual({ source: 'custom', id: 'inst-rhodes' })
  })

  it('falls back to the registry voice when no assignment', () => {
    expect(resolvePartInstrument(assignments, 'soul', 'melody', 'melody_lead'))
      .toEqual({ source: 'builtin', voice: 'melody_lead' })
    expect(resolvePartInstrument(null, 'soul', 'bass', null))
      .toEqual({ source: 'builtin', voice: null })
  })
})
