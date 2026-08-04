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
  matchDrumSlot,
  buildKit,
  setKitSlot,
  kitFiles,
  DRUM_SLOTS,
  KIT_ROOT,
  type InstrumentAssignments,
} from './customInstruments'

describe('isAudioFile', () => {
  it('accepts common audio extensions, rejects others', () => {
    for (const f of ['a.mp3', 'a.WAV', 'a.ogg', 'a.flac', 'a.m4a', 'a.aac']) expect(isAudioFile(f)).toBe(true)
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

// ── Drum kits ────────────────────────────────────────────────────────────────

const pitchOf = (id: string) => DRUM_SLOTS.find(s => s.id === id)!.pitch

describe('matchDrumSlot', () => {
  it('matches the obvious names', () => {
    expect(matchDrumSlot('kick.wav')?.id).toBe('kick')
    expect(matchDrumSlot('Snare_01.wav')?.id).toBe('snare')
    expect(matchDrumSlot('crash.wav')?.id).toBe('crash')
    expect(matchDrumSlot('ride.wav')?.id).toBe('ride')
    expect(matchDrumSlot('clap.wav')?.id).toBe('clap')
  })

  it('prefers open hat over closed when both words could match', () => {
    // "open hat" contains "hat", which is also the closed-hat cue — priority decides.
    expect(matchDrumSlot('open_hat.wav')?.id).toBe('open_hat')
    expect(matchDrumSlot('OpenHat 03.wav')?.id).toBe('open_hat')
    expect(matchDrumSlot('closed_hat.wav')?.id).toBe('closed_hat')
    expect(matchDrumSlot('hihat.wav')?.id).toBe('closed_hat')
  })

  it('accepts short abbreviations only as whole tokens', () => {
    expect(matchDrumSlot('BD.wav')?.id).toBe('kick')
    expect(matchDrumSlot('hh_01.wav')?.id).toBe('closed_hat')
    expect(matchDrumSlot('oh-2.wav')?.id).toBe('open_hat')
    // "chord" contains "ch" but is not a closed hat; "snippet" contains "sn".
    expect(matchDrumSlot('chord_stab.wav')).toBeNull()
    expect(matchDrumSlot('snippet.wav')).toBeNull()
  })

  it('distinguishes the toms', () => {
    expect(matchDrumSlot('tom1.wav')?.id).toBe('tom_hi')
    expect(matchDrumSlot('tom2.wav')?.id).toBe('tom_mid')
    expect(matchDrumSlot('floor_tom.wav')?.id).toBe('tom_lo')
  })

  it('returns null for anything it cannot place', () => {
    expect(matchDrumSlot('mystery.wav')).toBeNull()
    expect(matchDrumSlot('take_07.wav')).toBeNull()
  })
})

describe('buildKit', () => {
  it('files each sample on its GM pitch, rooted at a single zone', () => {
    const { kit, mapped, unmatched } = buildKit(['kick.wav', 'snare.wav', 'hh_closed.wav'])
    expect(mapped).toBe(3)
    expect(unmatched).toEqual([])
    expect(Object.keys(kit).map(Number).sort((a, b) => a - b))
      .toEqual([pitchOf('kick'), pitchOf('snare'), pitchOf('closed_hat')].sort((a, b) => a - b))
    // One zone per piece is what stops a kick being pitch-shifted into a ride.
    const kickLayers = kit[pitchOf('kick')].layers
    expect(kickLayers).toHaveLength(1)
    expect(Object.keys(kickLayers[0].urls)).toEqual([KIT_ROOT])
    expect(kickLayers[0].maxVelocity).toBe(1)
  })

  it('returns unplaceable files instead of guessing', () => {
    const { kit, mapped, unmatched } = buildKit(['kick.wav', 'weird_thing.wav'])
    expect(mapped).toBe(1)
    expect(unmatched).toEqual(['weird_thing.wav'])
    expect(Object.keys(kit)).toHaveLength(1)
  })

  it('builds velocity layers per piece from folder hints', () => {
    const { kit } = buildKit(['kick/soft/01.wav', 'kick/hard/01.wav', 'snare/hard/01.wav'])
    const kickLayers = kit[pitchOf('kick')].layers
    expect(kickLayers).toHaveLength(2)
    expect(kickLayers.map(l => l.maxVelocity)).toEqual([0.5, 1])
    // Softest first, and every layer still holds exactly the one kit zone.
    expect(kickLayers[0].urls[KIT_ROOT]).toBe('kick/soft/01.wav')
    expect(kickLayers[1].urls[KIT_ROOT]).toBe('kick/hard/01.wav')
    expect(kit[pitchOf('snare')].layers).toHaveLength(1)
  })

  it('groups round-robins within a piece, in rr order', () => {
    const { kit } = buildKit(['kick_rr2.wav', 'kick_rr1.wav'])
    expect(kit[pitchOf('kick')].layers[0].urls[KIT_ROOT]).toEqual(['kick_rr1.wav', 'kick_rr2.wav'])
  })

  it('ignores non-audio files', () => {
    const { mapped, skipped } = buildKit(['kick.wav', 'readme.txt'])
    expect(mapped).toBe(1)
    expect(skipped).toEqual(['readme.txt'])
  })
})

describe('setKitSlot', () => {
  it('places a file on a piece', () => {
    const kit = setKitSlot({}, pitchOf('ride'), ['whatever.wav'])
    expect(kit[pitchOf('ride')].layers[0].urls[KIT_ROOT]).toBe('whatever.wav')
  })

  it('given several files, groups them into velocity layers / round-robins by filename hint', () => {
    const kit = setKitSlot({}, pitchOf('kick'), ['kick_soft.wav', 'kick_hard.wav', 'kick_rr2_hard.wav'])
    const layers = kit[pitchOf('kick')].layers
    expect(layers).toHaveLength(2)
    expect(layers[0].urls[KIT_ROOT]).toBe('kick_soft.wav')
    expect(layers[1].urls[KIT_ROOT]).toEqual(['kick_hard.wav', 'kick_rr2_hard.wav'])
  })

  it('re-deriving a slot from an edited file list drops files no longer passed', () => {
    const withThree = setKitSlot({}, 36, ['a.wav', 'b.wav', 'c.wav'])
    const afterRemoveB = setKitSlot(withThree, 36, ['a.wav', 'c.wav'])
    expect(kitFiles(afterRemoveB)).toEqual(['a.wav', 'c.wav'])
  })

  it('clearing a piece removes it, so it falls back to the synth kit', () => {
    const kit = setKitSlot(setKitSlot({}, 36, ['a.wav']), 36, [])
    expect(kit[36]).toBeUndefined()
  })

  it('does not mutate the kit it was given', () => {
    const before = setKitSlot({}, 36, ['a.wav'])
    const after = setKitSlot(before, 38, ['b.wav'])
    expect(Object.keys(before)).toEqual(['36'])
    expect(Object.keys(after).sort()).toEqual(['36', '38'])
  })

  it('ignores non-audio paths rather than mapping them', () => {
    expect(setKitSlot({}, 36, ['notes.txt'])[36]).toBeUndefined()
  })
})

describe('kitFiles', () => {
  it('lists every referenced file once', () => {
    const { kit } = buildKit(['kick_rr1.wav', 'kick_rr2.wav', 'snare/soft/1.wav', 'snare/hard/1.wav'])
    expect(kitFiles(kit).sort()).toEqual(
      ['kick_rr1.wav', 'kick_rr2.wav', 'snare/hard/1.wav', 'snare/soft/1.wav'],
    )
  })
})

describe('resolvePartInstrument — per-style "built-in" override', () => {
  it('an empty per-style value beats the global default instead of inheriting it', () => {
    // Without this, choosing "Built-in" for one style would keep playing the
    // all-styles override — the assignment would look changed but sound identical.
    const assignments: InstrumentAssignments = {
      defaults: { chords: 'inst-rhodes' },
      perStyle: { jazz: { chords: '' } },
    }
    expect(resolvePartInstrument(assignments, 'jazz', 'chords', 'electric_piano_1'))
      .toEqual({ source: 'builtin', voice: 'electric_piano_1' })
    // Other styles still get the global default.
    expect(resolvePartInstrument(assignments, 'soul', 'chords', 'electric_piano_1'))
      .toEqual({ source: 'custom', id: 'inst-rhodes' })
  })
})
