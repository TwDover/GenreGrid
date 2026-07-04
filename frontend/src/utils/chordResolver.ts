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
const NOTE_INDEX: Record<string, number> = {
  C: 0, 'C#': 1, Db: 1, D: 2, 'D#': 3, Eb: 3,
  E: 4, F: 5, 'F#': 6, Gb: 6, G: 7, 'G#': 8, Ab: 8,
  A: 9, 'A#': 10, Bb: 10, B: 11,
}

const SCALE_INTERVALS: Record<string, number[]> = {
  major:      [0, 2, 4, 5, 7, 9, 11],
  minor:      [0, 2, 3, 5, 7, 8, 10],
  dorian:     [0, 2, 3, 5, 7, 9, 10],
  phrygian:   [0, 1, 3, 5, 7, 8, 10],
  lydian:     [0, 2, 4, 6, 7, 9, 11],
  mixolydian: [0, 2, 4, 5, 7, 9, 10],
  locrian:    [0, 1, 3, 5, 6, 8, 10],
  pentatonic: [0, 2, 4, 7, 9, 9, 9],
}

const FLAT_KEYS = new Set(['F', 'Bb', 'Eb', 'Ab', 'Db', 'Gb'])
const SHARP_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
const FLAT_NAMES  = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B']

function semitoneToNote(semi: number, keyRoot: string): string {
  return FLAT_KEYS.has(keyRoot) ? FLAT_NAMES[semi % 12] : SHARP_NAMES[semi % 12]
}

const ROMAN_DEGREE: Record<string, number> = { I: 0, II: 1, III: 2, IV: 3, V: 4, VI: 5, VII: 6 }

function parseRoman(symbol: string) {
  let s = symbol.trim()
  let accidental = 0
  if (s.startsWith('b')) { accidental = -1; s = s.slice(1) }
  else if (s.startsWith('#')) { accidental = 1; s = s.slice(1) }

  const m = s.match(/^(VII|VI|IV|V|III|II|I|vii|vi|iv|v|iii|ii|i)(.*)$/i)
  if (!m) return null

  const roman = m[1]
  const suffix = m[2] ?? ''
  const isMinor = roman === roman.toLowerCase()
  const degree = ROMAN_DEGREE[roman.toUpperCase()]
  if (degree === undefined) return null
  return { degree, accidental, isMinor, suffix }
}

export function resolveProgression(progression: string[], keyRoot: string, scale: string): string[] {
  const intervals = SCALE_INTERVALS[scale.toLowerCase()] ?? SCALE_INTERVALS.major
  const keyIdx = NOTE_INDEX[keyRoot] ?? 0

  return progression.map(symbol => {
    const parsed = parseRoman(symbol)
    if (!parsed) return symbol

    const { degree, accidental, isMinor, suffix } = parsed
    const scaleInterval = intervals[Math.min(degree, 6)] ?? 0
    const semi = (keyIdx + scaleInterval + accidental + 120) % 12
    const root = semitoneToNote(semi, keyRoot)

    let quality = ''
    const sfx = suffix.toLowerCase()
    if (sfx.includes('dim')) quality = 'dim'
    else if (sfx.includes('aug')) quality = 'aug'
    else if (isMinor) quality = 'm'

    let ext = ''
    if (suffix.includes('maj7')) ext = 'maj7'
    else if (suffix.includes('7')) ext = '7'
    else if (suffix.includes('sus4')) ext = 'sus4'
    else if (suffix.includes('sus2')) ext = 'sus2'
    else if (suffix.includes('add9') || suffix.includes('add2')) ext = 'add9'
    else if (suffix.includes('9')) ext = '9'

    return `${root}${quality}${ext}`
  })
}

export function scaleNotes(keyRoot: string, scale: string): Set<number> {
  const intervals = SCALE_INTERVALS[scale.toLowerCase()] ?? SCALE_INTERVALS.major
  const keyIdx = NOTE_INDEX[keyRoot] ?? 0
  return new Set(intervals.map(i => (keyIdx + i) % 12))
}
