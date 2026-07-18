# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Call-and-response: a short answering lick that fills a melody's silence.

Real arrangements are a dialogue — the lead phrases, then another voice answers
in the gap. This builds that answer from the song's melodic cell (the same
scale-step contour that seeds the chorus melody and the arpeggio), so the reply
RELATES to the call instead of being an unrelated filler. Shared by the bass
(low-register floor answer, present in every build) and the counter-melody
(distinct mid-register answer when that part is in the arrangement)."""
import random as _random
from typing import Callable, List

from app.services.midi_writer import NoteEvent
from app.theory.chords import roman_to_chord
from app.theory.scales import build_scale


def melody_cell(mel_events: list, key: str, scale: str, max_intervals: int = 4) -> list[int] | None:
    """Scale-step deltas of a melody's opening motif — the reusable 'cell'.

    Mirrors routes_song._melody_motif_intervals, but lives here (no app.api
    dependency) so the answer path can derive a cell from a section's own melody
    when the song-level cell doesn't exist yet — e.g. the first verse, whose
    theme hasn't been captured at the moment its backing is generated."""
    if not mel_events:
        return None
    lattice = build_scale(key, scale, octave_start=2, num_octaves=6)
    pitches = [e.pitch for e in sorted(mel_events, key=lambda e: e.start)[: max_intervals + 1]]
    if len(pitches) < 2:
        return None
    idxs = [min(range(len(lattice)), key=lambda i: abs(lattice[i] - p)) for p in pitches]
    intervals = [idxs[k + 1] - idxs[k] for k in range(len(idxs) - 1)]
    return intervals if any(intervals) else None


def build_answer_phrase(
    cell: list[int] | None,
    key: str,
    scale: str,
    chord_roman: str,
    rest_start: float,
    rest_end: float,
    lo: int,
    hi: int,
    channel: int,
    base_vel: int,
    rng: _random.Random,
    swing: Callable[[float], float] | None = None,
    invert: bool = True,
    note_dur: float = 0.42,
) -> List[NoteEvent]:
    """Return 2–4 eighth notes answering the melody inside [rest_start, rest_end].

    The notes follow the melodic `cell`'s scale-step contour (inverted by default
    so the answer MIRRORS the call — the classic question/answer shape), sit in
    the register `[lo, hi]`, always land their final note on a chord tone of
    `chord_roman`, start a hair after the rest opens, and finish a ~0.3-beat
    breath before it closes so they never collide with the melody's re-entry.

    Deterministic given `rng`; returns `[]` when the rest is too short or no
    usable material exists (caller then simply leaves the silence)."""
    if not cell or not any(cell):
        return []

    # Scale lattice clamped to the answering voice's register.
    lattice = [p for p in build_scale(key, scale, octave_start=1, num_octaves=7) if lo <= p <= hi]
    if len(lattice) < 3:
        return []

    try:
        chord_pcs = {p % 12 for p in roman_to_chord(chord_roman, key, scale, octave=4)}
    except Exception:
        chord_pcs = set()
    chord_idxs = [i for i, p in enumerate(lattice) if p % 12 in chord_pcs] or list(range(len(lattice)))

    # How many eighth notes fit, leaving a breath before the melody returns.
    first_t = rest_start + 0.12
    avail = (rest_end - 0.3) - first_t
    n = max(0, min(4, len(cell) + 1, int(avail / 0.5) + 1))
    if n < 2:
        return []

    # Open on a chord tone near the register centre, then walk the cell contour.
    centre = (lo + hi) / 2
    start_idx = min(chord_idxs, key=lambda i: abs(lattice[i] - centre))
    steps = [(-iv if invert else iv) for iv in cell[: n - 1]]
    idxs = [start_idx]
    for iv in steps:
        idxs.append(max(0, min(len(lattice) - 1, idxs[-1] + iv)))

    # Resolve the final note to the nearest chord tone (a lick that lands "off"
    # the chord reads as a mistake, not an answer).
    if chord_pcs and lattice[idxs[-1]] % 12 not in chord_pcs:
        idxs[-1] = min(chord_idxs, key=lambda i: abs(i - idxs[-1]))

    notes: List[NoteEvent] = []
    for k, si in enumerate(idxs[:n]):
        t = first_t + k * 0.5
        if t + note_dur * 0.8 > rest_end - 0.25:
            break
        start = swing(t) if swing else t
        vel = max(1, min(127, base_vel + rng.randint(-6, 6)))
        notes.append(NoteEvent(lattice[si], start, note_dur, vel, channel))
    return notes if len(notes) >= 2 else []
