# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Pure expansion/removal math for note regions (roadmap 9.2 follow-up)."""
from app.services.midi_writer import NoteEvent
from app.services.note_regions import expand_region, region_window, remove_expansion


def _n(pitch, start, duration=0.5, velocity=100, channel=0):
    return NoteEvent(pitch, start, duration, velocity, channel)


def test_region_window_spans_every_loop_repeat():
    # start_bar=2, bars=4, loop_count=3, 4 beats/bar → beats 8..(8+48)=56
    assert region_window(2, 4, 3) == (8.0, 56.0)
    assert region_window(0, 1, 1) == (0.0, 4.0)


def test_expand_region_repeats_relative_notes_at_each_loop_offset():
    notes = [_n(60, 0.0), _n(64, 1.0)]
    expanded = expand_region(notes, start_bar=1, bars=2, loop_count=2)
    starts = sorted((e.pitch, e.start) for e in expanded)
    # bar 1 → beat 4; repeat 2 bars later → beat 12
    assert starts == [(60, 4.0), (60, 12.0), (64, 5.0), (64, 13.0)]


def test_expand_region_single_loop_is_identity_shift():
    notes = [_n(60, 0.0, duration=1.0, velocity=90)]
    expanded = expand_region(notes, start_bar=0, bars=4, loop_count=1)
    assert len(expanded) == 1
    assert expanded[0].pitch == 60 and expanded[0].start == 0.0
    assert expanded[0].duration == 1.0 and expanded[0].velocity == 90


def test_remove_expansion_strips_exact_matches_bounded_to_window():
    region_notes = [_n(60, 0.0)]
    expansion = expand_region(region_notes, start_bar=0, bars=1, loop_count=1)  # one note at beat 0
    window = region_window(0, 1, 1)   # (0, 4)

    existing = [
        _n(60, 0.0),          # the region's own note — should be removed
        _n(62, 1.0),          # something else in-window, no match — orphan, kept
        _n(60, 8.0),          # content-identical note OUTSIDE the window — must survive
    ]
    remaining, orphans = remove_expansion(existing, expansion, window)
    remaining_keys = sorted((n.pitch, n.start) for n in remaining)
    assert remaining_keys == [(60, 8.0), (62, 1.0)]   # region note gone, both others survive
    assert orphans == 1   # the unmatched in-window note


def test_remove_expansion_never_touches_notes_outside_window_even_on_content_match():
    """The cross-song false-positive case flagged during planning: an unrelated
    note elsewhere that happens to be byte-identical to a region note must never
    be removed, even though a naive whole-part scan would match it."""
    region_notes = [_n(36, 0.0, duration=0.25, velocity=110)]   # a kick hit
    expansion = expand_region(region_notes, start_bar=0, bars=1, loop_count=1)
    window = region_window(0, 1, 1)

    # An identical kick hit recurring throughout the rest of the drum part.
    existing = [_n(36, 0.0, duration=0.25, velocity=110)] + [
        _n(36, float(bar * 4), duration=0.25, velocity=110) for bar in range(1, 10)
    ]
    remaining, orphans = remove_expansion(existing, expansion, window)
    assert orphans == 0
    # Only the in-window occurrence (bar 0) was removed; the other 9 survive untouched.
    assert len(remaining) == 9
    assert all(n.start >= 4.0 for n in remaining)
