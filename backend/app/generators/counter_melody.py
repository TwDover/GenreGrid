# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
import random
from typing import List

from app.services.midi_writer import NoteEvent
from app.theory.scales import build_scale
from app.theory.chords import roman_to_chord
from app.services.variation import should_trigger


def generate_counter_melody(
    melody_events: List[NoteEvent],
    key: str,
    scale: str,
    bars: int,
    progression: list | None = None,
    style: dict | None = None,
) -> List[NoteEvent]:
    """Harmony line derived from the melody — a diatonic 3rd/6th below.

    Follows the melody's rhythm but only on its structural notes (longer values,
    strong beats), so the harmony supports without doubling every ornament.
    On chord-change downbeats the harmony note snaps to the nearest chord tone
    below the melody so the interval always agrees with the sounding chord.
    Softer and slightly behind the lead in velocity so it reads as a backing
    voice, not a second lead.
    """
    if not melody_events:
        return []

    style = style or {}
    cm_cfg = style.get("counter_melody", {})
    vel_scale = cm_cfg.get("velocity_scale", 0.72)
    floor = cm_cfg.get("floor", 55)   # don't harmonize below this — muddiness guard

    beats_per_bar = 4
    prog_len = len(progression) if progression else 0

    # Scale lattice spanning below the melody register for stepping down 3rds/6ths
    scale_notes = build_scale(key, scale, octave_start=3, num_octaves=4)

    def _chord_pcs_at(beat: float) -> set[int]:
        if not progression:
            return set()
        chord_idx = int(beat / beats_per_bar) % prog_len
        return {p % 12 for p in roman_to_chord(progression[chord_idx], key, scale, octave=4)}

    events: List[NoteEvent] = []
    last_start = -1.0
    for note in sorted(melody_events, key=lambda e: e.start):
        beat_in_bar = note.start % beats_per_bar
        is_strong = (beat_in_bar % 1.0) < 0.13
        is_structural = note.duration >= 0.45 and is_strong
        if not is_structural:
            continue
        # Density guard: at most one harmony note per half-beat window
        if note.start - last_start < 0.5:
            continue

        # Nearest scale index at or below the melody pitch
        below = [i for i, n in enumerate(scale_notes) if n <= note.pitch]
        if not below:
            continue
        idx = below[-1]
        # Diatonic 3rd below (2 scale steps); occasionally a 6th for variety
        steps = 5 if should_trigger(0.22) else 2
        h_idx = max(0, idx - steps)
        pitch = scale_notes[h_idx]

        # On bar downbeats, prefer a chord tone: walk down until the pitch class
        # belongs to the sounding chord (bounded walk keeps us near the 3rd/6th).
        if beat_in_bar < 0.13:
            chord_pcs = _chord_pcs_at(note.start)
            walk = h_idx
            while chord_pcs and walk > 0 and scale_notes[walk] % 12 not in chord_pcs and h_idx - walk < 3:
                walk -= 1
            if chord_pcs and scale_notes[walk] % 12 in chord_pcs:
                pitch = scale_notes[walk]

        if pitch < floor or pitch >= note.pitch:
            continue

        events.append(NoteEvent(
            pitch=pitch,
            start=note.start + 0.012,   # a hair behind the lead — reads as backing
            duration=note.duration * 0.96,
            velocity=max(1, min(127, int(note.velocity * vel_scale))),
            channel=5,
        ))
        last_start = note.start

    return events
