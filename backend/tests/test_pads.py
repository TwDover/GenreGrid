# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
import random
from collections import defaultdict

from app.generators.pads import generate_pads


def _mean_pitch_by_bar(events, beats_per_bar=4):
    by_bar = defaultdict(list)
    for e in events:
        by_bar[int(e.start // beats_per_bar)].append(e.pitch)
    return {bar: sum(ps) / len(ps) for bar, ps in by_bar.items()}


def test_pads_basic():
    random.seed(7)
    events = generate_pads({}, "C", "major", bars=8, complexity=0.5, variation=0.3,
                           progression=["I", "vi", "IV", "V"])
    assert events
    for e in events:
        assert e.channel == 4
        assert 64 <= e.pitch <= 86   # default pad register


def test_pads_lift_above_the_melody():
    """A pad sharing the melody's octave masks the line into mush (measured: the
    melody was spending ~80% of its time inside the pad's pitch span, which read
    as "the melody and chords don't go together" even with zero note clash). Given
    the melody's top note, every pad note must sit strictly above it."""
    for seed in range(12):
        random.seed(seed)
        melody_top = 78
        events = generate_pads({}, "C", "minor", bars=8, complexity=0.6, variation=0.4,
                               progression=["i", "VI", "III", "VII"], melody_top=melody_top)
        assert events
        assert all(e.pitch > melody_top for e in events), \
            f"seed {seed}: a pad note fell into the melody's register (<= {melody_top})"


def test_pads_default_register_unchanged_without_melody():
    """With no melody to clear, pads keep their normal register (no regression
    for pad-only / melody-less sections)."""
    random.seed(3)
    events = generate_pads({}, "C", "major", bars=8, complexity=0.5, variation=0.3,
                           progression=["I", "vi", "IV", "V"], melody_top=None)
    assert events
    assert all(64 <= e.pitch <= 86 for e in events)


def test_pads_stay_stationary():
    """Pads must not leap registers between adjacent bars — the defining
    property of a pad layer is that it sits still while harmony changes.
    (Regression: the old voicing pipeline octave-shifted the whole voicing to
    fit the register after voice-leading, producing 12-semitone bar-to-bar
    jumps in generated songs.)"""
    for seed in range(10):
        random.seed(seed)
        events = generate_pads({}, "C", "minor", bars=12, complexity=0.7, variation=0.5,
                               progression=["i", "VI", "III", "VII"])
        means = _mean_pitch_by_bar(events)
        bars = sorted(means)
        for a, b in zip(bars, bars[1:]):
            if b == a + 1:
                assert abs(means[b] - means[a]) < 7, \
                    f"seed {seed}: pad center jumped {means[a]:.0f} -> {means[b]:.0f} at bar {b}"
