# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Section-level automation tests: pre-chorus CC74 filter sweeps (+ CC1 shadow)
and the CC11 crescendo into the chorus, unit-level and through build_song."""
import mido

from app.core.config import EXPORTS_DIR
from app.models.schemas import BuildSongRequest
from app.api.routes_song import build_song
from app.services.mixdown import (generate_build_sweeps, generate_section_crescendo,
                                  _PART_CHANNELS)


# Verse bars 0-8, pre-chorus bars 8-12 (beats 32-48), chorus bars 12-20.
_SECTIONS = [
    {"name": "Verse",      "section_type": "verse",      "bars": 8, "start_bar": 0,  "key": "C"},
    {"name": "Pre-Chorus", "section_type": "pre_chorus", "bars": 4, "start_bar": 8,  "key": "C"},
    {"name": "Chorus",     "section_type": "chorus",     "bars": 8, "start_bar": 12, "key": "C"},
    {"name": "End",        "section_type": "ending",     "bars": 1, "start_bar": 20, "key": "C"},
]
_PRE_START, _PRE_END = 32.0, 48.0   # pre-chorus span in beats


# ── generate_build_sweeps ─────────────────────────────────────────────────────

def test_sweep_cc74_confined_rising_and_reset():
    out = generate_build_sweeps(_SECTIONS, ["chords", "bass", "melody", "drums", "pads"])
    assert set(out) == {"chords", "pads"}
    for part in ("chords", "pads"):
        evs = out[part]
        assert all(e.channel == _PART_CHANNELS[part] for e in evs)
        ramp = sorted((e for e in evs if e.control == 74 and e.start < _PRE_END),
                      key=lambda e: e.start)
        assert ramp, "no CC74 sweep emitted"
        assert all(_PRE_START <= e.start < _PRE_END for e in ramp)
        values = [e.value for e in ramp]
        assert values == sorted(values) and len(set(values)) == len(values)  # strictly rising
        assert values[0] <= 45 and values[-1] >= 105
        resets = [e for e in evs if e.control == 74 and e.start == _PRE_END]
        assert len(resets) == 1 and resets[0].value == 84  # chorus downbeat, neutral


def test_sweep_cc1_shadows_cc74_at_half_depth():
    out = generate_build_sweeps(_SECTIONS, ["chords"])
    cc74 = sorted((e for e in out["chords"] if e.control == 74), key=lambda e: e.start)
    cc1 = sorted((e for e in out["chords"] if e.control == 1), key=lambda e: e.start)
    assert [(e.start, e.value // 2) for e in cc74] == [(e.start, e.value) for e in cc1]


def test_sweep_skips_absent_parts_and_songs_without_prechorus():
    assert set(generate_build_sweeps(_SECTIONS, ["chords", "bass"])) == {"chords"}
    assert generate_build_sweeps(_SECTIONS, ["bass", "melody", "drums"]) == {}
    no_pre = [s for s in _SECTIONS if s["section_type"] != "pre_chorus"]
    assert generate_build_sweeps(no_pre, ["chords", "pads"]) == {}


# ── generate_section_crescendo ────────────────────────────────────────────────

def test_crescendo_cc11_shape_reset_and_no_melody():
    parts = ["chords", "bass", "melody", "drums", "pads", "arpeggio"]
    out = generate_section_crescendo(_SECTIONS, parts)
    assert set(out) == {"chords", "pads", "arpeggio"}   # never melody (note-level swells live there)
    for part, evs in out.items():
        assert all(e.control == 11 and e.channel == _PART_CHANNELS[part] for e in evs)
        ramp = sorted((e for e in evs if e.start < _PRE_END), key=lambda e: e.start)
        assert all(_PRE_START <= e.start < _PRE_END for e in ramp)
        values = [e.value for e in ramp]
        assert values == sorted(values) and len(set(values)) == len(values)
        assert values[0] == 70 and values[-1] == 118
        resets = [e for e in evs if e.start == _PRE_END]
        assert len(resets) == 1 and resets[0].value == 100  # chorus downbeat


def test_crescendo_requires_a_following_chorus():
    sections = [dict(s) for s in _SECTIONS]
    sections[2]["section_type"] = "verse"   # pre-chorus now resolves into a verse
    assert generate_section_crescendo(sections, ["chords", "pads"]) == {}


# ── Integration: build_song writes the sweep into the chords stem ────────────

def _cc74_beats(path) -> list[float]:
    mid = mido.MidiFile(str(path))
    tpb = mid.ticks_per_beat
    beats = []
    for track in mid.tracks:
        t = 0
        for msg in track:
            t += msg.time
            if msg.type == "control_change" and msg.control == 74:
                beats.append(t / tpb)
    return beats


def test_built_song_chords_stem_has_prechorus_sweep():
    r = build_song(BuildSongRequest(
        style_id="synthwave", key="C", scale="minor", bpm=100,
        template="verse_chorus_bridge",
        parts=["chords", "bass", "melody", "drums", "pads"],
        seed=4242, use_priors=False))
    spans = {}
    for s in r.sections:
        spans.setdefault(s.section_type, []).append(
            (s.start_bar * 4.0, (s.start_bar + s.bars) * 4.0))
    assert spans.get("pre_chorus"), "template should contain pre-chorus sections"

    beats = _cc74_beats(EXPORTS_DIR / r.generation_id / "chords.mid")
    assert beats, "chords stem has no CC74 at all"
    in_pre = [b for b in beats if any(lo <= b < hi for lo, hi in spans["pre_chorus"])]
    assert in_pre, "no CC74 inside the pre-chorus spans"
    in_verse = [b for b in beats if any(lo <= b < hi for lo, hi in spans["verse"])]
    assert not in_verse, f"CC74 leaked into verse spans at beats {in_verse}"
