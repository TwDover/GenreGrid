# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
from app.generators.drums import generate_drums
from app.core.constants import DRUM_CHANNEL


def test_generate_drums_returns_events():
    style = {
        "drums": {
            "hat_density": 0.8,
            "triplet_probability": 0.0,
            "snare_standard_beats": [2, 4],
            "swing": 0.0,
        }
    }
    events = generate_drums(style, bars=4, complexity=0.5, variation=0.3)
    assert len(events) > 0
    for ev in events:
        assert ev.channel == DRUM_CHANNEL


def test_drums_always_has_kick_on_beat_one():
    style = {
        "drums": {
            "hat_density": 0.0,
            "triplet_probability": 0.0,
            "snare_standard_beats": [],
            "swing": 0.0,
        }
    }
    events = generate_drums(style, bars=2, complexity=0.0, variation=0.0)
    kick_pitch = 36
    kick_starts = [ev.start for ev in events if ev.pitch == kick_pitch]
    # Per-instrument timing jitter means kicks land within ±0.02 beats of the
    # quantized position rather than exactly on 0.0 / 4.0.
    _THRESHOLD = 0.03
    assert any(abs(s - 0.0) < _THRESHOLD for s in kick_starts), f"No kick near beat 1 in {kick_starts}"
    assert any(abs(s - 4.0) < _THRESHOLD for s in kick_starts), f"No kick near bar 2 beat 1 in {kick_starts}"


def _hits(events, pitches, lo=0.0, hi=1e9):
    return [e for e in events if e.pitch in pitches and lo <= e.start < hi]


def test_chorus_drums_open_up_vs_verse():
    """The drums must restate the section change: a chorus plays more hat rolls
    and open-hat offbeats than a verse of the same style (measured regression:
    verse and chorus bars were near-identical, which read as one static texture
    for the whole song)."""
    import random
    style = {"drums": {"hat_density": 0.6, "hat_roll_prob": 0.2,
                       "triplet_probability": 0.0, "snare_standard_beats": [2, 4],
                       "swing": 0.0}}

    def rolls_and_opens(section_type):
        rolls = opens = 0
        for seed in range(12):
            random.seed(seed)
            evs = generate_drums(style, bars=8, complexity=0.6, variation=0.3,
                                 is_loop=True, section_type=section_type)
            hats = sorted(e.start for e in evs if e.pitch == 42)
            rolls += sum(1 for a, b in zip(hats, hats[1:]) if 0.1 < b - a < 0.15)
            opens += len(_hits(evs, {46}))
        return rolls, opens

    v_rolls, v_opens = rolls_and_opens("verse")
    c_rolls, c_opens = rolls_and_opens("chorus")
    assert c_rolls > v_rolls * 1.5, f"chorus rolls {c_rolls} not > verse {v_rolls}"
    assert c_opens > v_opens, f"chorus open hats {c_opens} not > verse {v_opens}"


def test_section_reentry_gets_a_marker():
    """A non-chorus section start (which gets no crash) must still announce
    itself — an open hat rings over the first downbeat. Plain loop mode
    (no section_type) stays untouched."""
    import random
    style = {"drums": {"hat_density": 0.5, "triplet_probability": 0.0,
                       "snare_standard_beats": [2, 4], "swing": 0.0}}
    for seed in range(6):
        random.seed(seed)
        evs = generate_drums(style, bars=4, complexity=0.5, variation=0.3,
                             is_loop=True, section_type="verse")
        assert _hits(evs, {46}, -0.05, 0.3), f"seed {seed}: verse start has no marker"
        random.seed(seed)
        plain = generate_drums(style, bars=4, complexity=0.5, variation=0.3)
        assert not _hits(plain, {46}, -0.05, 0.3), f"seed {seed}: marker leaked into plain loop"


def test_fills_commit_or_stay_silent():
    """A section-end fill must never be decimated to a stray 1-2 hits by
    per-note probability: each fill bar carries either a real fill (>=3
    tom/snare hits beyond the backbeat) or nothing extra at all."""
    import random
    style = {"drums": {"hat_density": 0.5, "triplet_probability": 0.0,
                       "snare_standard_beats": [2, 4], "swing": 0.0}}
    lone = committed = 0
    for seed in range(40):
        random.seed(seed)
        evs = generate_drums(style, bars=4, complexity=0.6, variation=0.3,
                             is_loop=True, section_type="chorus",
                             section_end_bars=[3], next_section_type="verse")
        # fill window: last 1.25 beats of bar 3, excluding the beat-4 backbeat
        extra = [e for e in _hits(evs, {38, 40, 41, 43, 45, 47, 48, 50}, 14.75, 16.0)
                 if abs(e.start - 15.0) > 0.12]
        if len(extra) in (1, 2):
            lone += 1
        elif len(extra) >= 3:
            committed += 1
    assert committed > 0, "no fill ever committed in 40 seeds"
    assert lone == 0, f"{lone}/40 seeds produced a decimated 1-2 note fill"
