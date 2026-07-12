# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
from app.generators.bass import generate_bass


def test_generate_bass_returns_events():
    style = {
        "progression_templates": [["i", "VI", "III", "VII"]],
        "bass": {"pattern_density": 0.5, "octave_jumps": 0.0, "sustain_bias": 0.6},
    }
    events = generate_bass(style, "C", "minor", bars=4, complexity=0.5, variation=0.3)
    assert len(events) > 0
    for ev in events:
        assert ev.pitch >= 24
        assert ev.pitch <= 60
        assert ev.channel == 1


def test_808_bass_follows_two_chords_per_bar_grid():
    """Above harmony_complexity 0.6 the chords play 2 chords per bar. The 808
    must index the progression on that same grid — per-bar indexing left it
    sustaining the wrong chord's root for most of every high-complexity song
    (surfaced by the 500-song survey: bass_out_of_chord up to 69%)."""
    import random
    from app.theory.chords import roman_to_chord

    style = {"bass": {"bass_style": "808"}}
    prog = ["i", "VI", "III", "VII"]
    expected_pcs = [roman_to_chord(r, "C", "minor", octave=2)[0] % 12 for r in prog]
    for seed in range(5):
        random.seed(seed)
        events = generate_bass(style, "C", "minor", bars=4, complexity=0.75,
                               variation=0.3, progression=prog, harmony_complexity=0.75)
        assert events
        for e in events:
            window = int((e.start + 0.1) / 2.0) % len(prog)   # 2 beats per chord window
            assert e.pitch % 12 == expected_pcs[window], \
                f"seed {seed}: 808 at beat {e.start} plays pc {e.pitch % 12}, window {window} wants {expected_pcs[window]}"


def test_walking_bass_downbeats_follow_two_chords_per_bar_grid():
    """Walking bass beat-1 anchors (and beat-3 landings on mid-bar changes)
    must match the chord window sounding at that beat when the harmony runs
    at 2 chords per bar."""
    import random
    from app.theory.chords import roman_to_chord

    style = {"bass": {"bass_style": "walking"}}
    prog = ["i", "VI", "III", "VII"]
    expected_pcs = [roman_to_chord(r, "C", "minor", octave=2)[0] % 12 for r in prog]
    for seed in range(5):
        random.seed(seed)
        events = generate_bass(style, "C", "minor", bars=4, complexity=0.75,
                               variation=0.3, progression=prog, harmony_complexity=0.75)
        assert events
        for e in events:
            beat_in_bar = e.start % 4
            # Beat 1 (bar anchor) and beat 3 (mid-bar chord landing) are the
            # structural beats; beats 2/4 are walking/approach tones by design.
            if abs(beat_in_bar) < 0.15 or abs(beat_in_bar - 2.0) < 0.15:
                window = int((e.start + 0.1) / 2.0) % len(prog)
                assert e.pitch % 12 == expected_pcs[window], \
                    f"seed {seed}: walk at beat {e.start} plays pc {e.pitch % 12}, window {window} wants {expected_pcs[window]}"
