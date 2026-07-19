# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Rock/metal/doom/hip-hop support: power chords, double kick, dynamics macro."""
import json
import random
from pathlib import Path

from app.core.arrangement import (SECTION_PROFILES, apply_arrangement_dynamics,
                                  scaled_profile)
from app.core.constants import DRUM_MAP
from app.generators.chords import generate_chords
from app.generators.drums import generate_drums
from app.services.midi_writer import NoteEvent

STYLES_DIR = Path(__file__).parent.parent / "app" / "styles"


def _load(style_id: str) -> dict:
    return json.loads((STYLES_DIR / f"{style_id}.json").read_text(encoding="utf-8"))


# ── Power chords ──────────────────────────────────────────────────────────────

def test_power_chords_are_root_and_fifth_only():
    """Every sounded pitch class must be the chord's root or its 5th — no 3rds,
    no extensions, no voice-led inversions putting the 5th in the bass."""
    style = {**_load("metal"), "progression_templates": [["i", "i", "i", "i"]]}
    for seed in range(5):
        random.seed(seed)
        events = generate_chords(style, "C", "minor", bars=4, complexity=0.5,
                                 variation=0.3, progression=["i", "i", "i", "i"],
                                 resolved_progression=["i", "i", "i", "i"])
        assert events
        for ev in events:
            assert ev.pitch % 12 in {0, 7}, \
                f"seed {seed}: pitch {ev.pitch} is not C-root/5th"
        # Full hits keep the root on the bottom (partial comp hits — a lone
        # chug on one voice — are fine, so only check 2+-note onsets)
        by_start: dict[float, list[int]] = {}
        for ev in events:
            by_start.setdefault(round(ev.start, 1), []).append(ev.pitch)
        for start, group in by_start.items():
            if len(group) >= 2:
                assert min(group) % 12 == 0, \
                    f"seed {seed}: 5th in the bass at beat {start}"


def test_power_chords_respect_register():
    style = _load("doom_metal")
    lo, hi = style["chord_register"]
    random.seed(3)
    events = generate_chords(style, "E", "minor", bars=4, complexity=0.5,
                             variation=0.3, progression=["i", "bVI", "i", "bVII"],
                             resolved_progression=["i", "bVI", "i", "bVII"])
    assert events
    for ev in events:
        assert lo <= ev.pitch <= hi


# ── Double kick ───────────────────────────────────────────────────────────────

def test_double_kick_fills_sixteenths():
    style = {"drums": {"double_kick_prob": 1.0, "snare_standard_beats": [2, 4]}}
    random.seed(1)
    events = generate_drums(style, bars=4, complexity=0.5, variation=0.3)
    kicks_by_bar: dict[int, int] = {}
    for ev in events:
        if ev.pitch == DRUM_MAP["kick"]:
            kicks_by_bar[int(ev.start // 4)] = kicks_by_bar.get(int(ev.start // 4), 0) + 1
    # prob 1.0 (clamped to 0.9 per-bar): most bars must be full 16th runs
    full_bars = sum(1 for n in kicks_by_bar.values() if n >= 15)
    assert full_bars >= 2, f"expected 16th-note kick bars, got {kicks_by_bar}"


def test_double_kick_absent_by_default():
    random.seed(1)
    events = generate_drums({"drums": {}}, bars=4, complexity=0.5, variation=0.3)
    for bar in range(4):
        kicks = [e for e in events
                 if e.pitch == DRUM_MAP["kick"] and bar * 4 <= e.start < (bar + 1) * 4]
        assert len(kicks) < 10


# ── Dynamics macro ────────────────────────────────────────────────────────────

def test_scaled_profile_neutral_at_half():
    for stype in SECTION_PROFILES:
        assert scaled_profile(stype, 0.5) == SECTION_PROFILES[stype]


def test_scaled_profile_widens_and_flattens():
    base = SECTION_PROFILES["chorus"]["complexity_scale"]   # > 1
    assert scaled_profile("chorus", 1.0)["complexity_scale"] > base
    flat = scaled_profile("chorus", 0.0)["complexity_scale"]
    assert 1.0 < flat < base
    v_base = SECTION_PROFILES["intro"]["complexity_scale"]  # < 1
    assert scaled_profile("intro", 1.0)["complexity_scale"] < v_base
    assert v_base < scaled_profile("intro", 0.0)["complexity_scale"] < 1.0


def _dummy_song(n_events_per_part: int = 400):
    """Two verses + two choruses of dense events on every part."""
    sections = [
        {"section_type": "verse",  "start_bar": 0,  "bars": 8},
        {"section_type": "chorus", "start_bar": 8,  "bars": 8},
        {"section_type": "verse",  "start_bar": 16, "bars": 8},
        {"section_type": "chorus", "start_bar": 24, "bars": 8},
    ]
    total_beats = 32 * 4
    events = {}
    for part in ("drums", "bass", "chords", "pads", "arpeggio", "melody"):
        step = total_beats / n_events_per_part
        events[part] = [NoteEvent(60 if part != "drums" else 38,
                                  round(i * step, 3), 0.1, 80, 0)
                        for i in range(n_events_per_part)]
    return events, sections


def test_arrangement_dynamics_scales_stripping():
    """Aggregated over seeds, dynamics=1 must strip strictly more events than
    dynamics=0 — the macro's whole point. Melody is never stripped."""
    def total_left(dynamics: float) -> int:
        left = 0
        for seed in range(30):
            events, sections = _dummy_song()
            apply_arrangement_dynamics(events, sections, seed, dynamics=dynamics)
            left += sum(len(v) for v in events.values())
        return left

    assert total_left(1.0) < total_left(0.0)


def test_arrangement_dynamics_never_strips_chorus_melody():
    """The verse-1 late-entry device may strip early verse melody, but the
    melody must always carry the choruses — it's the voice that survives
    every drop and breakdown."""
    for seed in range(10):
        events, sections = _dummy_song()
        chorus_windows = [(s["start_bar"] * 4.0, (s["start_bar"] + s["bars"]) * 4.0)
                          for s in sections if s["section_type"] == "chorus"]
        before = sum(1 for e in events["melody"]
                     if any(lo <= e.start < hi for lo, hi in chorus_windows))
        apply_arrangement_dynamics(events, sections, seed, dynamics=1.0)
        after = sum(1 for e in events["melody"]
                    if any(lo <= e.start < hi for lo, hi in chorus_windows))
        assert after == before


# ── Per-section comp variants ─────────────────────────────────────────────────

def _onset_positions(events) -> set[float]:
    """Distinct within-bar 8th-note positions the comp hits (strums collapsed)."""
    return {round((e.start % 4) * 2) / 2 for e in events}


def test_comp_section_variants_change_the_rhythm():
    """Rock's guitar must NOT chug the same 8ths through every section: verses
    are sparser than choruses and intros ring instead of driving (measured
    before the fix: one identical rhythm fingerprint across all 81 bars)."""
    style = _load("rock")
    prog = ["I", "IV", "V", "IV"]

    def gen(section_type):
        random.seed(11)
        return generate_chords(style, "A", "major", bars=4, complexity=0.5,
                               variation=0.3, progression=prog,
                               resolved_progression=prog, section_type=section_type)

    chorus_pos = _onset_positions(gen("chorus"))
    verse_pos = _onset_positions(gen("verse"))
    intro_pos = _onset_positions(gen("intro"))
    assert len(verse_pos) < len(chorus_pos), (verse_pos, chorus_pos)
    assert len(intro_pos) <= 2, intro_pos          # pad_hold: bar-start rings only
    # No section context (plain loop) keeps the style's base comp
    assert _onset_positions(gen(None)) == chorus_pos


def test_comp_variants_ignored_without_style_knob():
    style = {"comp_style": "pad_hold"}
    prog = ["I", "vi", "I", "vi"]
    random.seed(2)
    a = generate_chords(style, "C", "major", bars=2, complexity=0.4, variation=0.3,
                        progression=prog, resolved_progression=prog,
                        section_type="chorus")
    random.seed(2)
    b = generate_chords(style, "C", "major", bars=2, complexity=0.4, variation=0.3,
                        progression=prog, resolved_progression=prog)
    assert [(e.start, e.pitch) for e in a] == [(e.start, e.pitch) for e in b]


# ── New styles sanity ─────────────────────────────────────────────────────────

def test_new_styles_generate_all_parts():
    from app.generators.bass import generate_bass
    from app.generators.melody import generate_melody
    for style_id in ("rock", "metal", "doom_metal", "hip_hop"):
        style = _load(style_id)
        prog = style["progression_templates"][0]
        key = style["preferred_keys"][0]
        scale = style["default_scale"]
        random.seed(7)
        assert generate_chords(style, key, scale, 4, 0.5, 0.3,
                               progression=prog, resolved_progression=prog)
        assert generate_drums(style, 4, 0.5, 0.3)
        assert generate_bass(style, key, scale, 4, 0.5, 0.3, prog, [0.0, 4.0, 8.0, 12.0])
        assert generate_melody(style, key, scale, 4, 0.6, 0.3, prog)
