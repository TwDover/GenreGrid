# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
from app.core.constants import NOTE_NAMES


def note_name_to_midi(name: str, octave: int = 4) -> int:
    """Convert note name + octave to MIDI number. Middle C (C4) = 60."""
    name = name.strip()
    # Normalize flats to sharps
    flat_map = {"Db": "C#", "Eb": "D#", "Fb": "E", "Gb": "F#", "Ab": "G#", "Bb": "A#", "Cb": "B"}
    name = flat_map.get(name, name)
    if name not in NOTE_NAMES:
        raise ValueError(f"Unknown note name: {name}")
    return (octave + 1) * 12 + NOTE_NAMES.index(name)


def midi_to_note_name(midi: int) -> str:
    return NOTE_NAMES[midi % 12]


def midi_to_octave(midi: int) -> int:
    return (midi // 12) - 1


def note_root_midi(key: str, octave: int = 4) -> int:
    return note_name_to_midi(key, octave)
