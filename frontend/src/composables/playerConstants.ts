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

// Shared player constants — style-behaviour classification and the MIDI
// channel <-> part mapping. Split out of useMidiPlayer.ts so both live playback
// and the offline WAV render read one source (no duplication, no import cycle).

// Styles where ALL parts use synthesis — drum/bass samplers are not loaded
export const SYNTH_STYLES = new Set([
  'house', 'techno', 'drum_and_bass', 'synthwave', 'future_bass', 'jersey_club',
  'grime', 'hyperpop',
])
// Styles that load sampled drums/bass but use a synth lead for melodic parts
export const MELODIC_SYNTH_STYLES = new Set(['drill', 'dark_trap', 'reggaeton', 'dancehall'])
// Styles that use a slow-attack pad synth for melodic (sampled drums/bass still load)
export const PAD_STYLES = new Set([
  'ambient', 'dark_ambient', 'epic_orchestral', 'cinematic',
  'trap_soul', 'cloud_rap',
])
// Lo-fi styles — warm, bit-crushed synth for melodic
export const LOFI_STYLES = new Set(['lofi'])

export const PLAYER_PARTS = ['drums', 'bass', 'chords', 'melody', 'arpeggio', 'pads', 'counter_melody'] as const
export type PlayerPart = typeof PLAYER_PARTS[number]

// MIDI channel → part name (see backend _PART_CHANNELS; 9 = GM percussion)
export const CHANNEL_PART: Record<number, PlayerPart> = {
  0: 'chords', 1: 'bass', 2: 'melody', 3: 'arpeggio', 4: 'pads', 5: 'counter_melody', 9: 'drums',
}
