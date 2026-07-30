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
import { resolveMelodicVoiceKind, panFromCC10, type VoiceContext } from './voiceRouting'

const base: VoiceContext = {
  channel: 0, hasPatch: false, hasCustom: false, hasSampler: false, voiceId: null,
  isLofi: false, isSynth: false, isMelodicSynth: false, isPad: false, hasPiano: false,
}
const ctx = (o: Partial<VoiceContext>) => resolveMelodicVoiceKind({ ...base, ...o })

describe('resolveMelodicVoiceKind — precedence', () => {
  it('a designed patch wins over everything, including a custom instrument', () => {
    expect(ctx({ hasPatch: true, hasCustom: true, hasSampler: true, isSynth: true, channel: 4 })).toBe('synth_patch')
  })
  it('custom instrument wins over everything except a patch', () => {
    expect(ctx({ hasCustom: true, hasSampler: true, isSynth: true, channel: 4 })).toBe('custom')
  })
  it('a loaded sampler wins over identity-lead and style family', () => {
    expect(ctx({ hasSampler: true, channel: 2, voiceId: 'melody_lead', isSynth: true })).toBe('sampler')
  })
  it('part-specific channels (4/5/3) beat the style family', () => {
    expect(ctx({ channel: 4, isLofi: true })).toBe('pad')       // pads part before isLofi
    expect(ctx({ channel: 5, isSynth: true })).toBe('strings')  // counter-melody before isSynth
    expect(ctx({ channel: 3, isPad: true })).toBe('arp_pluck')  // arpeggio before isPad
  })
})

describe('resolveMelodicVoiceKind — identity + families', () => {
  it('melody_lead identity gives the soft lead, but only on the melody channel', () => {
    expect(ctx({ channel: 2, voiceId: 'melody_lead' })).toBe('melody_lead_soft')
    // a melody_lead id on the arp channel is ignored — arp still gets its pluck
    expect(ctx({ channel: 3, voiceId: 'melody_lead' })).toBe('arp_pluck')
  })
  it('lofi routes every melodic part to the lo-fi synth', () => {
    expect(ctx({ channel: 0, isLofi: true })).toBe('lofi')
    expect(ctx({ channel: 2, isLofi: true })).toBe('lofi')
  })
  it('synth / melodic-synth: chords get the comp, melody the lead', () => {
    expect(ctx({ channel: 0, isSynth: true })).toBe('synth_chords')
    expect(ctx({ channel: 2, isSynth: true })).toBe('synth_lead')
    expect(ctx({ channel: 0, isMelodicSynth: true })).toBe('synth_chords')
    expect(ctx({ channel: 2, isMelodicSynth: true })).toBe('synth_lead')
  })
  it('pad styles: chords hold the pad, melody gets a fast-attack lead', () => {
    expect(ctx({ channel: 0, isPad: true })).toBe('pad')
    expect(ctx({ channel: 2, isPad: true })).toBe('melody_lead_soft')
  })
  it('piano fallback when available, else the synth default', () => {
    expect(ctx({ channel: 0, hasPiano: true })).toBe('piano')
    expect(ctx({ channel: 2, hasPiano: true })).toBe('piano')
    expect(ctx({ channel: 0 })).toBe('synth_chords')  // no flags, no piano
    expect(ctx({ channel: 2 })).toBe('synth_lead')
  })
})

describe('panFromCC10', () => {
  it('centres when there is no CC10', () => {
    expect(panFromCC10(undefined)).toBe(0)
    expect(panFromCC10([])).toBe(0)
  })
  it('maps the last 0..1 value into -1..1', () => {
    expect(panFromCC10([{ value: 0.5 }])).toBe(0)
    expect(panFromCC10([{ value: 1 }])).toBe(1)
    expect(panFromCC10([{ value: 0 }])).toBe(-1)
    expect(panFromCC10([{ value: 0 }, { value: 1 }])).toBe(1)   // last wins
  })
  it('clamps out-of-range values to the rails', () => {
    expect(panFromCC10([{ value: 5 }])).toBe(1)
    expect(panFromCC10([{ value: -5 }])).toBe(-1)
  })
})
