# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Roadmap v3 item 11.1 — the phrase plan drives the chords.

`plan_phrases` decides each 4-bar phrase is *open* (half cadence) or *closed*,
and the melody lands on sd2/sd5 or the tonic accordingly — but the harmony
underneath just kept cycling the section's template, so a melody landing "open"
over whatever chord happened to fall there did not read as a half cadence.

Three invariants are pinned here:
  * the plan and the harmony agree — open phrases end on dominant harmony,
    closed phrases on the tonic, and *only* the phrase-final slot moves;
  * the tiled progression `align_cadences` returns is index-identical to the
    template it came from everywhere it did not rewrite, which is what lets the
    gate-off path stay byte-identical for every consumer;
  * styles opt in — `cadence_alignment` defaults to 0 and a vamp stays a vamp.
"""
import random

import pytest

from app.generators.chords import align_cadences, _split_suffix
from app.generators.melody import generate_melody
from app.models.schemas import GenerateRequest
from app.services.generation import _run_attempt
from app.services.style_loader import load_style
from app.theory.phrase_plan import PhrasePlan

PARTS = ["chords", "bass", "melody", "drums"]
SEED = 20260805


def _plan(cadence_open: bool) -> PhrasePlan:
    return PhrasePlan(role="statement", contour_peak=0.55, register=0.5,
                      density_mult=1.0, cadence_open=cadence_open,
                      replay_motif=0.0, climax=False)


def _style(style_id="rock", **over):
    return {**load_style(style_id), "_humanize_scale": 0.5, **over}


def _req(**over):
    base = dict(style_id="rock", key="C", scale="major", bpm=110, bars=8,
                complexity=0.5, variation=0.4, parts=PARTS, mode="arrangement")
    return GenerateRequest(**{**base, **over})


# ── the rewrite itself ────────────────────────────────────────────────────────

@pytest.mark.parametrize("cpb", [1, 2])
def test_open_phrase_ends_on_dominant_closed_phrase_ends_on_tonic(cpb):
    prog = ["I", "vi", "IV", "ii"]
    out = align_cadences(prog, "major", bars=8, chords_per_bar=cpb,
                         plans=[_plan(True), _plan(False)])
    slots_per_phrase = 4 * cpb
    assert out[slots_per_phrase - 1] == "V"
    assert out[2 * slots_per_phrase - 1] == "I"


def test_minor_closes_on_the_minor_tonic():
    out = align_cadences(["i", "bVI", "bIII", "iv"], "minor", bars=4,
                         chords_per_bar=1, plans=[_plan(False)])
    assert out[3] == "i"


def test_only_the_phrase_final_slot_moves():
    prog = ["i", "bVI", "bIII", "iv"]
    plans = [_plan(True), _plan(False)]
    out = align_cadences(prog, "minor", bars=8, chords_per_bar=1, plans=plans)
    moved = {i for i, r in enumerate(out) if r != prog[i % len(prog)]}
    assert moved <= {3, 7}, "a mid-phrase chord was rewritten"


def test_untouched_slots_index_exactly_like_the_template():
    """The returned progression is tiled to whole template cycles, so every
    consumer's `progression[i % len(progression)]` — at one chord per bar, two
    per bar, or the lookahead one past the section's end — reads the same chord
    it read before. That identity is the whole reason the gate-off path can
    claim byte-identical output."""
    prog = ["I", "vi", "IV", "V", "ii", "V"]           # 6 chords, 8 bars: no clean tiling
    plans = [_plan(True), _plan(False)]
    out = align_cadences(prog, "major", bars=8, chords_per_bar=1, plans=plans)
    assert len(out) % len(prog) == 0
    rewritten = {3, 7}
    for i in range(3 * len(out)):
        if i % len(out) in rewritten:
            continue
        assert out[i % len(out)] == prog[i % len(prog)], f"slot {i} drifted"


def test_truncated_final_phrase_cadences_on_the_sections_last_chord():
    """6 bars is one full phrase plus half of another. The short phrase's
    nominal final slot (bar 8) never sounds, so its cadence lands on the last
    chord the section actually plays."""
    out = align_cadences(["I", "vi", "IV", "ii"], "major", bars=6,
                         chords_per_bar=1, plans=[_plan(True), _plan(False)])
    assert out[3] == "V"
    assert out[5] == "I"


# ── chord quality and vocabulary ──────────────────────────────────────────────

@pytest.mark.parametrize("roman,expected", [
    ("IVsus2", "Vsus2"),      # colour, not function — kept
    ("IV6",    "V6"),
    ("IVmaj7", "V"),          # would make the dominant a major 7th — dropped
    ("imM7",   "V"),
    ("iv",     "V"),
])
def test_cadence_keeps_only_quality_neutral_suffixes(roman, expected):
    out = align_cadences(["I", "vi", "IV", roman], "major", bars=4,
                         chords_per_bar=1, plans=[_plan(True)])
    assert out[3] == expected


def test_split_suffix_reads_the_whole_roman_vocabulary():
    assert _split_suffix("V9sus4") == ("V", "9sus4")
    assert _split_suffix("imM7") == ("i", "mM7")
    assert _split_suffix("bVII") == ("bVII", "")
    assert _split_suffix("I6") == ("I", "6")


def test_the_tonic_chords_quality_comes_from_the_progression_not_the_scale():
    """R&B writes I ♭VI I IV over a minor scale. Closing that on "i" because the
    scale says minor imports a chord the song never uses."""
    out = align_cadences(["I", "bVI", "I", "IV"], "minor", bars=4,
                         chords_per_bar=1, plans=[_plan(False)])
    assert out[3] == "I"


def test_modal_minor_progression_cadences_on_its_own_subtonic():
    """A ♭VII-based rock/folk progression has no leading tone anywhere in it;
    forcing a harmonic-minor V there would be a chord from another song."""
    out = align_cadences(["i", "bVII", "bVI", "bVII"], "minor", bars=4,
                         chords_per_bar=1, plans=[_plan(True)])
    assert out[3] == "bVII"


def test_minor_progression_that_already_uses_V_gets_V():
    out = align_cadences(["i", "iv", "V", "bVII"], "minor", bars=4,
                         chords_per_bar=1, plans=[_plan(True)])
    assert out[3] == "V"


@pytest.mark.parametrize("scale", ["pentatonic_minor", "pentatonic_major",
                                   "blues", "locrian", "whole_tone"])
def test_scales_without_a_functional_dominant_are_left_alone(scale):
    """Roman degrees are positional: on a five-note scale "V" names the fifth
    scale *note* (the ♭7 in pentatonic_minor), and locrian's fifth is
    diminished. Neither is a half cadence, so the harmony stays as written."""
    prog = ["i", "bVI", "bIII", "iv"]
    assert align_cadences(prog, scale, bars=4, chords_per_bar=1,
                          plans=[_plan(True)]) == prog


def test_no_plans_returns_the_progression_untouched():
    prog = ["I", "vi", "IV", "V"]
    assert align_cadences(prog, "major", bars=4, chords_per_bar=1, plans=[]) == prog


# ── the melody obeys the same plan ────────────────────────────────────────────

def _notes(evts):
    return [(round(e.start, 3), e.pitch, e.velocity) for e in sorted(evts, key=lambda e: e.start)]


def test_the_supplied_plan_replaces_the_melodys_own_draw(monkeypatch):
    """If `generate_melody` kept planning for itself, the harmony would cadence
    against a phrase form the melody never agreed to."""
    import app.generators.melody as melody_mod
    drawn = []
    monkeypatch.setattr(melody_mod, "plan_phrases",
                        lambda n: drawn.append(n) or [_plan(False)] * n)

    random.seed(3)
    generate_melody(_style(), "C", "major", 8, 0.5, 0.4, ["I", "vi", "IV", "ii"],
                    phrase_plans=[_plan(True), _plan(False)])
    assert drawn == [], "melody drew its own plan on top of the one it was given"

    random.seed(3)
    generate_melody(_style(), "C", "major", 8, 0.5, 0.4, ["I", "vi", "IV", "ii"])
    assert drawn == [2], "melody stopped planning for callers that don't opt in"


def test_the_supplied_plan_changes_the_line():
    """The plan is consumed, not just accepted: an open→closed period (the
    antecedent/consequent pass answers the question and lands it) is not the
    same line as two closed phrases."""
    style = _style()
    lines = []
    for plans in ([_plan(True), _plan(False)], [_plan(False), _plan(False)]):
        random.seed(5)
        lines.append(_notes(generate_melody(style, "C", "major", 8, 0.5, 0.4,
                                            ["I", "vi", "IV", "ii"],
                                            phrase_plans=plans)))
    assert lines[0] != lines[1]


def test_melody_without_plans_still_plans_for_itself():
    """Every caller that does not opt in must behave exactly as before — same
    seed, same notes."""
    style = _style()
    random.seed(7)
    a = generate_melody(style, "C", "major", 8, 0.5, 0.4, ["I", "vi", "IV", "ii"])
    random.seed(7)
    b = generate_melody(style, "C", "major", 8, 0.5, 0.4, ["I", "vi", "IV", "ii"])
    assert _notes(a) == _notes(b)


# ── end to end through _run_attempt ───────────────────────────────────────────

def _resolved_sections(req, style):
    """Capture the harmony `_run_attempt` reports to the scorer."""
    import app.services.quality as quality_mod
    captured = {}
    original = quality_mod._build_chord_map_from_sections

    def _spy(sections, key, scale):
        captured["sections"] = sections
        return original(sections, key, scale)

    quality_mod._build_chord_map_from_sections = _spy
    try:
        _run_attempt(req, style, SEED, False, style.get("groove_push", 0.0),
                     style.get("secondary_dominants", False),
                     style.get("tritone_substitution", False))
    finally:
        quality_mod._build_chord_map_from_sections = original
    return captured.get("sections") or []


def test_every_phrase_of_a_generated_song_cadences_as_planned():
    """The done-when for 11.1: at `cadence_alignment: 1.0` every open phrase of
    every section ends on dominant harmony and every closed one on the tonic —
    checked against the very plan the melody was handed."""
    from app.core.arrangement import _part_seed
    from app.theory.phrase_plan import plan_phrases

    style = _style("rock", cadence_alignment=1.0)
    sections = _resolved_sections(_req(bars=16), style)
    assert sections
    checked = 0
    for i, sec in enumerate(sections):
        romans, cpb, bars = sec["romans"], sec["chords_per_bar"], sec["bars"]
        random.seed(_part_seed(SEED, i, "phrase_plan"))
        plans = plan_phrases(max(1, (bars + 3) // 4))
        for p, plan in enumerate(plans):
            end = min((p + 1) * 4 * cpb, bars * cpb)
            assert romans[end - 1] == ("V" if plan.cadence_open else "I"), \
                f"section {i} phrase {p} ({plan.role}): {romans}"
            checked += 1
    assert checked >= len(sections), "no phrase was checked"


@pytest.mark.parametrize("style_id", ["house", "techno", "lofi", "ambient"])
def test_vamp_styles_never_cadence(style_id):
    """A loop that never comes to rest is what these styles ARE — opting them in
    would be a bug, not an upgrade."""
    assert load_style(style_id).get("cadence_alignment", 0.0) == 0.0


def test_a_zero_gate_is_the_same_as_no_gate_at_all():
    with_zero = dict(_style("rock"), cadence_alignment=0.0)
    without = {k: v for k, v in with_zero.items() if k != "cadence_alignment"}
    assert [s["romans"] for s in _resolved_sections(_req(), with_zero)] == \
           [s["romans"] for s in _resolved_sections(_req(), without)]


def test_pre_chorus_keeps_the_ramp_progression_it_was_handed():
    """The song builder swaps a pre-chorus's whole progression to ramp into the
    chorus; a cadence rewrite on top of that would undo the ramp."""
    style = _style("rock", cadence_alignment=1.0)
    req = _req(bars=4, mode="loop", section_type="pre_chorus")
    fixed = ["ii", "IV", "vi", "V"]
    _e, _c, _p, _prog, _q, _pats, _secs = _run_attempt(
        req, style, 4242, True, style.get("groove_push", 0.0), False, False,
        fixed_progression=fixed)
    plain = _run_attempt(req, {**style, "cadence_alignment": 0.0}, 4242, True,
                         style.get("groove_push", 0.0), False, False,
                         fixed_progression=fixed)
    for part in PARTS:
        assert [(e.pitch, e.start) for e in _e[part]] == \
               [(e.pitch, e.start) for e in plain[0][part]], part
