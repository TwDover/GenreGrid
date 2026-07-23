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
// The live player synthesizes every drum kit (see synthDrums.ts, makeSynthKit).
// This module only maps a style → a synth-kit "character". The old sampled kits
// (getDrumKit / Tone.Players over /samples/drums/) were removed: they had no
// callers, and the Tone.js drum samples they used carry no confirmed license
// (see docs/LICENSE_AUDIT.md). STYLE_TO_KIT's names are retained purely as keys
// into the character map below.
const STYLE_TO_KIT: Record<string, string> = {
  // Acoustic kit — live drum feel
  jazz:            'acoustic-kit',
  bossa_nova:      'acoustic-kit',
  latin_jazz:      'acoustic-kit',
  samba:           'acoustic-kit',
  afrobeats:       'acoustic-kit',
  afropop:         'acoustic-kit',
  cumbia:          'acoustic-kit',
  epic_orchestral: 'acoustic-kit',
  cinematic:       'acoustic-kit',
  // LinnDrum — classic vintage machine; punchy with natural decay
  soul:            'LINN',
  rnb:             'LINN',
  funk:            'LINN',
  // KPR77 — mellow, dusty; perfect for lo-fi and atmospheric
  lofi:            'KPR77',
  cloud_rap:       'KPR77',
  ambient:         'KPR77',
  dark_ambient:    'KPR77',
  // Roland R-8 — clean, digital punch; dembow/riddim patterns
  dancehall:       'R8',
  reggaeton:       'R8',
  baile_funk:      'R8',
  // Breakbeats — hip-hop sample chops
  boom_bap:        'breakbeat8',
  trap_soul:       'breakbeat8',
  dark_trap:       'breakbeat13',
  drill:           'breakbeat13',
  // Electronic / club — Techno kit (tight, synthetic)
  house:           'Techno',
  techno:          'Techno',
  drum_and_bass:   'Techno',
  future_bass:     'Techno',
  synthwave:       'Techno',
  jersey_club:     'Techno',
  // grime + hyperpop use SYNTH_STYLES → makeSynthDrums(), no kit loaded
}
const DEFAULT_KIT = 'acoustic-kit'

// Map each kit to a synthesized-drum character preset (see synthDrums.ts).
const KIT_TO_CHARACTER: Record<string, import('./synthDrums').DrumCharacter> = {
  'acoustic-kit': 'acoustic',
  LINN:           'punchy',
  KPR77:          'lofi',
  CR78:           'vintage',
  R8:             'digital',
  Techno:         'techno',
  breakbeat8:     'breakbeat',
  breakbeat13:    'breakbeat',
}

/** Resolve the synthesized-drum character for a style (used by the live player). */
export function drumCharacterForStyle(styleId?: string): import('./synthDrums').DrumCharacter {
  // Styles without a mapped kit (grime, hyperpop) were pure-synthesis before —
  // give them a hard electronic character.
  const kit = (styleId && STYLE_TO_KIT[styleId]) ?? (styleId ? 'Techno' : DEFAULT_KIT)
  return KIT_TO_CHARACTER[kit] ?? 'acoustic'
}
