# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
from app.core.constants import SCALE_INTERVALS, NOTE_NAMES
from app.theory.notes import note_name_to_midi


def build_scale(key: str, scale: str, octave_start: int = 3, num_octaves: int = 3) -> list[int]:
    """Return list of MIDI notes for the given key/scale across num_octaves."""
    intervals = SCALE_INTERVALS.get(scale)
    if intervals is None:
        raise ValueError(f"Unknown scale: {scale}")
    root = note_name_to_midi(key, octave_start)
    notes = []
    for oct_offset in range(num_octaves):
        for interval in intervals:
            note = root + oct_offset * 12 + interval
            if 0 <= note <= 127:
                notes.append(note)
    return notes


def scale_degree_to_midi(key: str, scale: str, degree: int, octave: int = 4) -> int:
    """Get MIDI for a scale degree (0-indexed) in the given key/scale/octave."""
    intervals = SCALE_INTERVALS.get(scale)
    if intervals is None:
        raise ValueError(f"Unknown scale: {scale}")
    root = note_name_to_midi(key, octave)
    oct_extra, idx = divmod(degree, len(intervals))
    return root + oct_extra * 12 + intervals[idx]
