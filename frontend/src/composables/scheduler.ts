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

// The per-note callbacks the live-playback Tone.Part scheduler fires. Pulled out of
// useMidiPlayer's toggle() so the fragile bits — mute gating, the drum sidechain
// pump, and the trigger arguments — are unit-testable without a Tone context: every
// collaborator (the kit/voice, the mute check, midi->note, the duck) is injected.

export interface DrumKitLike {
  trigger(midi: number, velocity: number, time: number): void
}
export interface VoiceLike {
  triggerAttackRelease(note: string, duration: number, time: number, velocity: number): void
}

export interface DrumNote { midi: number; velocity: number }
export interface VoiceNote { midi: number; duration: number; velocity: number }

// Drum part: skip when the drums part is muted; trigger the kit; and on electronic
// styles (`pump`) briefly duck the other buses on each kick (GM kick = midi 36).
export function drumTriggerCallback(
  kit: DrumKitLike,
  isMuted: () => boolean,
  pump: boolean,
  duckOnKick: (time: number) => void,
): (time: number, note: DrumNote) => void {
  return (time, note) => {
    if (isMuted()) return
    kit.trigger(note.midi, note.velocity, time)
    if (pump && note.midi === 36) duckOnKick(time)
  }
}

// Pitched part (bass / chords / melody / arp / pads / counter): skip when muted,
// else play the note (midi -> note name) for its duration at its time/velocity.
export function voiceTriggerCallback(
  voice: VoiceLike,
  isMuted: () => boolean,
  midiToNote: (midi: number) => string,
): (time: number, note: VoiceNote) => void {
  return (time, note) => {
    if (isMuted()) return
    voice.triggerAttackRelease(midiToNote(note.midi), note.duration, time, note.velocity)
  }
}
