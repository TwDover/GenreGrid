# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
from app.theory.chords import roman_to_chord
from app.generators.chords import generate_chords


def test_roman_major_triad():
    notes = roman_to_chord("I", "C", "major", octave=4)
    assert len(notes) == 3
    assert notes[0] == 60  # C4


def test_roman_minor_triad():
    notes = roman_to_chord("i", "C", "minor", octave=4)
    assert len(notes) == 3
    assert notes[0] == 60


def test_roman_with_7th():
    notes = roman_to_chord("i", "C", "minor", octave=4, allow_7th=True)
    assert len(notes) == 4


def test_generate_chords_returns_events():
    style = {
        "progression_templates": [["i", "VI", "III", "VII"]],
        "chord_extensions": {"allow_7th": 0.0, "allow_9th": 0.0},
    }
    events = generate_chords(style, "C", "minor", bars=4, complexity=0.5, variation=0.3)
    assert len(events) > 0
    for ev in events:
        assert 0 <= ev.pitch <= 127
        assert ev.velocity > 0


def test_sparse_comp_rhythm_still_sounds_every_chord_window():
    """At 2 chords per bar (harmony_complexity > 0.6), a comp rhythm whose hits
    all sit in the bar's first half (pad_hold's [1,0,0,...]) used to leave the
    second chord window silent — every other chord of the progression was
    dropped while the first rang through it. Every window must sound its chord."""
    import random

    style = {"comp_style": "pad_hold"}
    prog = ["I", "vi", "I", "vi"]
    for seed in range(5):
        random.seed(seed)
        events = generate_chords(style, "C", "major", bars=4, complexity=0.75,
                                 variation=0.3, progression=prog,
                                 resolved_progression=prog, harmony_complexity=0.75)
        # Each 2-beat window must contain at least one note, and window notes
        # must not ring across into the next window.
        for w in range(8):
            w_start = w * 2.0
            in_window = [e for e in events if w_start - 0.2 <= e.start < w_start + 1.8]
            assert in_window, f"seed {seed}: chord window {w} is silent"
        for e in events:
            # +0.1 tolerance: humanize jitter can fire a window's chord a few
            # ms before the window boundary.
            w_start = ((e.start + 0.1) // 2.0) * 2.0
            assert e.start + e.duration <= w_start + 2.3, \
                f"seed {seed}: chord at {e.start} rings {e.duration} beats across the next window"


def test_declutter_opens_internal_semitone_clusters():
    """Voice-leading an extended chord in a register capped below the melody can
    pack a tension (the 9th) a semitone from a core tone — a Cm9 collapses to a
    C-D-Eb grind that reads as mud, not a chord. The de-cluster pass must leave
    no two voiced notes a semitone apart in the same chord (block-comp styles)."""
    import random
    from collections import defaultdict
    from app.services.style_loader import load_style

    for style_id in ("cloud_rap", "trap_soul"):
        style = load_style(style_id)
        clustered = total = 0
        for seed in range(20):
            random.seed(seed)
            events = generate_chords(style, "C", "minor", bars=8, complexity=0.6,
                                     variation=0.3, progression=["i", "VI", "III", "VII"],
                                     resolved_progression=["i", "VI", "III", "VII"],
                                     harmony_complexity=0.5, melody_ceiling=60)
            by_onset = defaultdict(list)
            for e in events:
                by_onset[round(e.start, 2)].append(e.pitch)
            for ps in by_onset.values():
                ps = sorted(set(ps))
                total += 1
                if any(b - a == 1 for a, b in zip(ps, ps[1:])):
                    clustered += 1
        # allow a tiny residue (a triad-only maj7 crunch with no room to open)
        assert clustered / total < 0.03, \
            f"{style_id}: {100*clustered/total:.0f}% of chords still cluster"


def test_declutter_keeps_a_playable_chord_and_the_core_triad():
    """De-cluster must never strip a chord below its triad, and must keep the
    root/3rd/5th (it only drops tensions / an unspreadable maj7)."""
    import random
    from app.services.style_loader import load_style

    style = load_style("cloud_rap")
    for seed in range(20):
        random.seed(seed)
        events = generate_chords(style, "C", "minor", bars=8, complexity=0.7,
                                 variation=0.4, progression=["i", "VI", "III", "VII"],
                                 resolved_progression=["i", "VI", "III", "VII"],
                                 harmony_complexity=0.5, melody_ceiling=60)
        from collections import defaultdict
        by_onset = defaultdict(list)
        for e in events:
            by_onset[round(e.start, 2)].append(e.pitch)
        for ps in by_onset.values():
            assert len(set(p % 12 for p in ps)) >= 3, "chord thinned below a triad"
