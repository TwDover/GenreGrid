# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Read a MIDI file into structured per-channel note events (in beats)."""
from dataclasses import dataclass
from pathlib import Path

import mido


@dataclass
class Note:
    start: float      # beats from song start
    duration: float   # beats
    pitch: int
    velocity: int
    channel: int


@dataclass
class MidiSong:
    notes: list[Note]
    ppq: int          # ticks per beat
    total_beats: float

    def by_channel(self) -> dict[int, list[Note]]:
        out: dict[int, list[Note]] = {}
        for n in self.notes:
            out.setdefault(n.channel, []).append(n)
        for ns in out.values():
            ns.sort(key=lambda x: x.start)
        return out

    def pitched_notes(self) -> list[Note]:
        """All non-drum notes (channel 9 is the GM drum channel)."""
        return [n for n in self.notes if n.channel != 9]


def read_song(path: str | Path) -> MidiSong:
    """Parse a MIDI file into a flat list of Note events measured in beats.

    Note-on/note-off pairing is done per (channel, pitch); a note-on with
    velocity 0 counts as a note-off (running-status convention).
    """
    mid = mido.MidiFile(str(path))
    ppq = mid.ticks_per_beat or 480
    notes: list[Note] = []
    max_tick = 0

    for track in mid.tracks:
        abs_tick = 0
        # (channel, pitch) -> (start_tick, velocity); a small stack per key handles
        # repeated note-ons before a note-off.
        pending: dict[tuple[int, int], list[tuple[int, int]]] = {}
        for msg in track:
            abs_tick += msg.time
            if msg.type == "note_on" and msg.velocity > 0:
                pending.setdefault((msg.channel, msg.note), []).append((abs_tick, msg.velocity))
            elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
                key = (msg.channel, msg.note)
                stack = pending.get(key)
                if stack:
                    start_tick, vel = stack.pop(0)
                    dur = max(1, abs_tick - start_tick)
                    notes.append(Note(
                        start=start_tick / ppq,
                        duration=dur / ppq,
                        pitch=msg.note,
                        velocity=vel,
                        channel=msg.channel,
                    ))
                    max_tick = max(max_tick, abs_tick)

    notes.sort(key=lambda n: (n.start, n.pitch))
    return MidiSong(notes=notes, ppq=ppq, total_beats=max_tick / ppq if ppq else 0.0)
