# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Phase 2 of the instrument-identity design: playing profiles shape generation.

A sax melody must be monophonic with breath gaps and stay inside the horn's
range (including the climax octave-up extension); chord voicings must fit the
instrument's polyphony; a bass part must not dip below its instrument's lowest
note. See docs/instrument-identity-design.md §5.
"""
import random

from app.generators.melody import generate_melody
from app.generators.chords import generate_chords, _cap_polyphony
from app.generators.bass import generate_bass
from app.core.instruments import INSTRUMENTS, clamp_range

SAX_STYLE = {
    "id": "t",
    "instrumentation": {"melody": "alto_sax"},
    "melody": {"density": 0.75, "stepwise_motion": 0.7, "leap_probability": 0.15,
               "rest_probability": 0.1, "range": [60, 79], "phrase_climax_prob": 1.0},
}


def test_clamp_range():
    assert clamp_range([60, 91], [49, 81]) == [60, 81]
    assert clamp_range([40, 60], [49, 81]) == [49, 60]
    assert clamp_range([90, 96], [49, 81]) == [90, 96]   # disjoint → style wins


def test_sax_melody_is_monophonic_with_breaths_and_in_range():
    lo, hi = INSTRUMENTS["alto_sax"]["range"]
    for seed in range(5):
        random.seed(seed)
        events = sorted(generate_melody(SAX_STYLE, "C", "minor", bars=8,
                                        complexity=0.7, variation=0.4,
                                        progression=["i", "VI", "III", "VII"]),
                        key=lambda e: e.start)
        assert events
        # In range — the climax phrase (probability forced to 1.0) must not
        # push the line above the horn's top.
        for e in events:
            assert lo <= e.pitch <= hi, f"seed {seed}: {e.pitch} outside sax range"
        # Monophonic: no overlaps (allow float fuzz)
        for a, b in zip(events, events[1:]):
            assert a.start + a.duration <= b.start + 1e-6, \
                f"seed {seed}: overlap at {a.start:.2f}"
        # Breath: no continuous sounding span longer than ~8.6 beats
        span_start, last_end = None, None
        for e in events:
            if last_end is None or e.start - last_end >= 0.25:
                span_start = e.start
            end = e.start + e.duration
            assert end - span_start <= 8.6, f"seed {seed}: {end - span_start:.1f}-beat span with no breath"
            last_end = end


def test_cap_polyphony_keeps_outer_voices():
    voicing = [48, 52, 55, 59, 62, 66]
    capped = _cap_polyphony(voicing, 4)
    assert len(capped) == 4
    assert capped[0] == 48 and capped[-1] == 66   # bass + soprano survive
    assert _cap_polyphony(voicing, None) == voicing
    assert _cap_polyphony([60, 64], 4) == [60, 64]


def test_chords_respect_instrument_polyphony():
    style = {
        "id": "t",
        "instrumentation": {"chords": "clavinet"},   # polyphony 4
        "chord_extensions": {"allow_7th": 1.0, "allow_9th": 1.0},   # push voicings to 5 notes
    }
    prog = ["i", "VI", "III", "VII"]
    for seed in range(5):
        random.seed(seed)
        events = generate_chords(style, "C", "minor", bars=4, complexity=0.5,
                                 variation=0.3, progression=prog, resolved_progression=prog)
        # group by near-simultaneous onset (strum window)
        events.sort(key=lambda e: e.start)
        group: list = []
        group_start = None
        for e in events:
            if group_start is None or e.start - group_start <= 0.12:
                group.append(e)
                group_start = group[0].start
            else:
                assert len(group) <= 4, f"seed {seed}: {len(group)}-voice hit on a 4-voice instrument"
                group = [e]
                group_start = e.start


def test_bass_folds_into_instrument_range():
    style = {
        "id": "t",
        "instrumentation": {"bass": "upright_bass"},   # range 28-60
        "bass": {"pattern_density": 0.6, "octave_jumps": 0.3, "sustain_bias": 0.5},
    }
    lo, hi = INSTRUMENTS["upright_bass"]["range"]
    for seed in range(5):
        random.seed(seed)
        events = generate_bass(style, "A", "minor", bars=4, complexity=0.6,
                               variation=0.4, progression=["i", "VI", "III", "VII"])
        assert events
        for e in events:
            assert lo <= e.pitch <= hi, f"seed {seed}: bass note {e.pitch} outside upright range"
