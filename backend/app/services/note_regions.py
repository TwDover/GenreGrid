# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Pure expansion/removal math for note regions (roadmap 9.2 follow-up) — a
recorded MIDI take (9.1) tracked as an independent, movable, loopable region on
a part's timeline. No I/O here; `routes_song.py` handles reading/writing stems
and song_meta.json around these functions.

A region's `notes` are its exact recorded content, relative to the region's own
start (beat 0 = region start). The part's on-disk stem always holds the
*expansion* of that content: `loop_count` copies, each `bars` bars apart,
starting at `start_bar` — merged in alongside whatever else is on the part.
Bars are always 4 beats, matching the existing convention elsewhere in the note-
editing path (e.g. `_generate_part_cc`'s per-bar sustain loop in mixdown.py).
"""
from app.services.midi_writer import NoteEvent

BEATS_PER_BAR = 4


def region_window(start_bar: int, bars: int, loop_count: int,
                   beats_per_bar: int = BEATS_PER_BAR) -> tuple[float, float]:
    """The absolute (start_beat, end_beat) span a region's full expansion
    occupies — every loop repeat, back-to-back."""
    start_beat = start_bar * beats_per_bar
    end_beat = start_beat + bars * loop_count * beats_per_bar
    return start_beat, end_beat


def expand_region(notes: list[NoteEvent], start_bar: int, bars: int, loop_count: int,
                   beats_per_bar: int = BEATS_PER_BAR) -> list[NoteEvent]:
    """Repeat a region's relative note content `loop_count` times, placed at
    absolute beats starting at `start_bar`, each repeat `bars` bars later."""
    start_beat = start_bar * beats_per_bar
    bar_beats = bars * beats_per_bar
    expanded: list[NoteEvent] = []
    for k in range(loop_count):
        offset = start_beat + k * bar_beats
        for n in notes:
            expanded.append(NoteEvent(pitch=n.pitch, start=n.start + offset,
                                       duration=n.duration, velocity=n.velocity,
                                       channel=n.channel))
    return expanded


def remove_expansion(existing: list[NoteEvent], expansion: list[NoteEvent],
                      window: tuple[float, float], tol: float = 1e-3) -> tuple[list[NoteEvent], int]:
    """Remove `expansion`'s notes from `existing` by exact (pitch, start,
    duration, velocity) match — bounded to `window` (a region's own absolute
    span). Never removes anything outside `window`, even if it happens to
    content-match: an identical note elsewhere on the part (plausible for
    drums' small pitch/duration/velocity alphabet) must survive untouched.

    A note inside the window that doesn't find an exact match (e.g. hand-edited
    since the region was last synced) is left behind as an accepted "orphan" —
    returned in the orphan count, not silently dropped.
    """
    def in_window(n: NoteEvent) -> bool:
        return window[0] - tol <= n.start < window[1] - tol

    def close(a: NoteEvent, b: NoteEvent) -> bool:
        return (a.pitch == b.pitch and a.velocity == b.velocity
                and abs(a.start - b.start) <= tol and abs(a.duration - b.duration) <= tol)

    remaining: list[NoteEvent] = []
    to_remove = list(expansion)
    orphan_count = 0
    for n in existing:
        if not in_window(n):
            remaining.append(n)
            continue
        match_idx = next((i for i, e in enumerate(to_remove) if close(n, e)), None)
        if match_idx is None:
            remaining.append(n)   # in-window but unmatched: leave it (orphan)
            orphan_count += 1
        else:
            to_remove.pop(match_idx)
    return remaining, orphan_count
