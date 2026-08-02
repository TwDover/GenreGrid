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

// Pure voice-routing decision for live playback — which instrument a melodic part
// plays, given its MIDI channel and the style's classification. Extracted from
// useMidiPlayer's getMelodicInstrument so the branch logic (the fragile bit) is
// unit-testable in isolation; the actual Tone node construction stays in the
// composable and switches on the kind this returns.

// channel: 0 = chords, 2 = melody, 3 = arpeggio, 4 = pads, 5 = counter-melody
export interface VoiceContext {
  channel: number
  hasPatch: boolean             // a user-designed synth patch is assigned to this part
  hasCustom: boolean            // a user custom instrument is assigned to this part
  hasSampler: boolean           // a sampled (identity) voice loaded for this part
  voiceId: string | null        // resolved instrument-identity id for this part
  isLofi: boolean
  isSynth: boolean
  isMelodicSynth: boolean
  isPad: boolean
  hasPiano: boolean             // the shared Salamander piano is available
}

export type MelodicVoiceKind =
  | 'synth_patch'      // a user-designed patch (built via buildSynthFromPatch)
  | 'custom'            // the user's assigned instrument (returned as-is)
  | 'sampler'           // the loaded identity sampler (returned as-is)
  | 'melody_lead_soft'  // makeMelodyLead(true)
  | 'synth_lead'        // makeMelodyLead(false)
  | 'synth_chords'      // makeSynthChords
  | 'pad'               // makePad
  | 'strings'           // makeStrings
  | 'arp_pluck'         // makeArpPluck
  | 'lofi'              // makeLofiSynth
  | 'piano'             // the shared piano (returned as-is)

// Mirrors getMelodicInstrument's original branch ORDER exactly — the first match
// wins, so patch > custom > sampler > identity-lead > part-specific voice > style
// family > piano > synth default. A user-designed patch is the most explicit intent,
// so it wins over everything, the way custom/sampler win over the style defaults.
export function resolveMelodicVoiceKind(c: VoiceContext): MelodicVoiceKind {
  if (c.hasPatch) return 'synth_patch'
  if (c.hasCustom) return 'custom'
  if (c.hasSampler) return 'sampler'
  if (c.channel === 2 && c.voiceId === 'melody_lead') return 'melody_lead_soft'
  if (c.channel === 4) return 'pad'                    // pads part — always the sustained wash
  if (c.channel === 5) return 'strings'                // counter-melody — soft strings
  if (c.channel === 3) return 'arp_pluck'              // arpeggio — its own pluck
  if (c.isLofi) return 'lofi'
  if (c.isSynth || c.isMelodicSynth) return c.channel === 0 ? 'synth_chords' : 'synth_lead'
  if (c.isPad) return c.channel === 0 ? 'pad' : 'melody_lead_soft'
  if (c.hasPiano) return 'piano'
  return c.channel === 0 ? 'synth_chords' : 'synth_lead'
}

// Static pan a track was written with: @tonejs/midi normalises CC10 to 0..1; the
// last value wins, mapped to the -1..1 a Tone.Panner expects. No CC10 => centre.
export function panFromCC10(cc: ReadonlyArray<{ value: number }> | undefined): number {
  if (cc && cc.length) return Math.max(-1, Math.min(1, cc[cc.length - 1].value * 2 - 1))
  return 0
}

// A hand-drawn volume/pan automation breakpoint (roadmap 9.3): time in seconds
// at the track's native tempo (matching ParsedNote.time), value normalized 0..1
// (@tonejs/midi already normalises CC bytes this way). A single breakpoint is
// the same as today's static CC10 read — the "curve" degenerates cleanly.
export interface AutomationBreakpoint { time: number; value: number }

export function curveFromCC(cc: ReadonlyArray<{ time: number; value: number }> | undefined): AutomationBreakpoint[] {
  return cc ? cc.map(e => ({ time: e.time, value: e.value })).sort((a, b) => a.time - b.time) : []
}
