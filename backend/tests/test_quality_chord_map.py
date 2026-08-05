# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Roadmap v3 item 10.1 — the scorer judges the chords that actually sound.

`resolve_progression` rewrites each section's harmony (7th/9th swaps, secondary
dominants, tritone subs) and the melody is generated against *that*; choruses can
also sit in a lifted key and change chords twice as fast. The scorer used to
rebuild its chord map by tiling the raw pre-substitution progression, so any
attempt that used a substitution was judged against chords nobody played.

These tests pin the substituted map as the one that gets scored.
"""
import pytest

from app.models.schemas import GenerateRequest
from app.services.midi_writer import NoteEvent
from app.services.quality import (
    _build_chord_map, _build_chord_map_from_sections, score_generation,
)
from app.services.style_loader import load_style
from app.theory.chords import roman_to_chord


def _style(style_id="lofi"):
    return {**load_style(style_id), "_humanize_scale": 0.5}


def _pcs(roman: str, key: str = "C", scale: str = "minor") -> set[int]:
    return {p % 12 for p in roman_to_chord(roman, key, scale, octave=4,
                                           allow_7th=True, allow_9th=True)}


def _section(romans, *, offset=0.0, bars=4, key="C", bar_beats=4.0, cpb=1):
    return {"offset": offset, "bars": bars, "key": key,
            "bar_beats": bar_beats, "chords_per_bar": cpb, "romans": list(romans)}


# ── the map itself ────────────────────────────────────────────────────────────

def test_map_uses_substituted_romans_not_the_template():
    """A tritone sub (V -> bII) must put bII's pitch classes in the slot."""
    raw = ["i", "iv", "V", "i"]
    resolved = ["i", "iv", "bII", "i"]          # what resolve_progression produced

    from_template = _build_chord_map(raw, "C", "minor", 4, 0.5)
    from_sections = _build_chord_map_from_sections([_section(resolved)], "C", "minor")

    # Slot 3 (beats 8-12) is the substituted chord in both maps.
    assert from_template[2][2] == _pcs("V")
    assert from_sections[2][2] == _pcs("bII")
    assert from_sections[2][2] != from_template[2][2], "substitution must change the map"


def test_map_honours_a_sections_shifted_key():
    """A chorus-lift section resolves its romans in the lifted key, not req.key."""
    romans = ["i", "VI", "III", "VII"]
    in_c = _build_chord_map_from_sections([_section(romans, key="C")], "C", "minor")
    in_e = _build_chord_map_from_sections([_section(romans, key="E")], "C", "minor")

    assert in_c[0][2] == _pcs("i", key="C")
    assert in_e[0][2] == _pcs("i", key="E")
    assert in_c[0][2] != in_e[0][2]


def test_map_honours_two_chords_per_bar():
    """Choruses raise the chord rate; slots must be half-bars, not whole bars.

    The generators pick chords-per-bar from `harmony_complexity`, which the
    scorer never saw — it used the request's global complexity, so a boosted
    chorus was scored on slots twice as long as the ones being played.
    """
    romans = ["i", "VI", "III", "VII"]
    fast = _build_chord_map_from_sections([_section(romans, bars=2, cpb=2)], "C", "minor")

    assert len(fast) == 4                                   # 2 bars x 2 chords
    assert [slot[0] for slot in fast] == [0.0, 2.0, 4.0, 6.0]
    assert fast[1][2] == _pcs("VI")                         # beat 2 is already chord 2


def test_map_offsets_and_orders_multiple_sections():
    """Each section's slots start at its own offset, and the map stays sorted."""
    sections = [
        _section(["i", "iv"], offset=0.0,  bars=2),
        _section(["V", "i"],  offset=8.0,  bars=2, key="E"),
    ]
    chord_map = _build_chord_map_from_sections(sections, "C", "minor")

    assert [slot[0] for slot in chord_map] == [0.0, 4.0, 8.0, 12.0]
    assert chord_map == sorted(chord_map, key=lambda slot: slot[0])
    assert chord_map[2][2] == _pcs("V", key="E")


def test_map_respects_non_four_four_bar_length():
    """Slot width follows the section's own bar length (3/4 -> 3-beat bars)."""
    waltz = _build_chord_map_from_sections(
        [_section(["i", "iv"], bars=2, bar_beats=3.0)], "C", "minor")
    assert [slot[0] for slot in waltz] == [0.0, 3.0]
    assert waltz[0][1] == 3.0


def test_map_skips_sections_with_no_harmony():
    assert _build_chord_map_from_sections([_section([])], "C", "minor") == []


# ── what it does to the score ─────────────────────────────────────────────────

def _melody_on(pcs: set[int], n: int = 8) -> list[NoteEvent]:
    """A melody made only of the given pitch classes, one note per beat."""
    ordered = sorted(pcs)
    return [NoteEvent(60 + ordered[i % len(ordered)], float(i), 1.0, 90, 2)
            for i in range(n)]


def test_harmonic_score_follows_the_substituted_chord():
    """A melody spelling bII scores well against the resolved map and badly
    against the raw one — the exact inversion that made the search avoid
    adventurous harmony."""
    raw = ["bII"] * 4          # pretend the template said V and the section resolved to bII
    resolved = ["bII"] * 4
    melody = _melody_on(_pcs("bII"))
    events = {"melody": melody, "chords": [], "bass": [], "drums": []}

    scored_wrong = score_generation(events, _style(), "C", "minor", 8,
                                    ["V"] * 4, 0.5)
    scored_right = score_generation(events, _style(), "C", "minor", 8,
                                    ["V"] * 4, 0.5,
                                    resolved_sections=[_section(resolved, bars=8)])

    assert scored_right["harmonic"] > scored_wrong["harmonic"]
    assert scored_right["harmonic"] > 0.95, "every note is a chord tone of what sounds"
    # Sanity: scoring the raw map against a raw-matching progression agrees.
    assert score_generation(events, _style(), "C", "minor", 8, raw, 0.5)["harmonic"] \
        == pytest.approx(scored_right["harmonic"], abs=0.02)


def test_omitting_resolved_sections_keeps_legacy_behaviour():
    """Callers that don't pass sections must score exactly as before."""
    melody = _melody_on(_pcs("i"))
    events = {"melody": melody, "chords": [], "bass": [], "drums": []}
    prog = ["i", "VI", "III", "VII"]

    a = score_generation(events, _style(), "C", "minor", 8, prog, 0.5)
    b = score_generation(events, _style(), "C", "minor", 8, prog, 0.5,
                         resolved_sections=[])          # empty == not supplied
    assert a == b


def test_style_match_still_reads_the_raw_progression():
    """`_style_match` compares against corpus bigrams mined from template-level
    romans, so it must keep seeing the un-substituted progression."""
    from app.services.quality import _style_match

    style = _style("jazz")
    melody = _melody_on(_pcs("i"))
    raw = ["ii", "V", "I", "vi"]
    score_raw, _ = _style_match(raw, melody, style)
    if score_raw is None:
        pytest.skip("no corpus prior for jazz in this checkout")
    # The scorer receives `progression`, never `resolved_sections`, for this dim.
    events = {"melody": melody, "chords": [], "bass": [], "drums": []}
    with_sections = score_generation(events, style, "C", "minor", 8, raw, 0.5,
                                     resolved_sections=[_section(["bII"] * 4, bars=8)])
    # score_generation rounds to 3 dp; _style_match returns full precision.
    assert with_sections["style_match"] == pytest.approx(round(score_raw, 3), abs=1e-9)


# ── end-to-end through the generator ──────────────────────────────────────────

def test_run_attempt_reports_sections_matching_its_own_harmony():
    """The section records handed to the scorer must describe the real grid:
    one entry per section, covering the whole request, with resolved romans."""
    from app.services.generation import _run_attempt

    style = _style("jazz")
    req = GenerateRequest(style_id="jazz", key="C", scale="minor", bars=16,
                          mode="arrangement", complexity=0.7, seed=4242)
    captured = {}

    import app.services.quality as quality_mod
    original = quality_mod._build_chord_map_from_sections

    def _spy(sections, key, scale):
        captured["sections"] = sections
        return original(sections, key, scale)

    quality_mod._build_chord_map_from_sections = _spy
    try:
        _run_attempt(req, style, 4242, False, style.get("groove_push", 0.0),
                     style.get("secondary_dominants", False),
                     style.get("tritone_substitution", False))
    finally:
        quality_mod._build_chord_map_from_sections = original

    sections = captured.get("sections")
    assert sections, "score_generation was not given resolved sections"
    assert sum(s["bars"] for s in sections) == 16
    assert [s["offset"] for s in sections] == sorted(s["offset"] for s in sections)
    for s in sections:
        assert s["romans"], "a section reported no harmony"
        assert s["chords_per_bar"] in (1, 2)
        assert s["bar_beats"] == 4.0
