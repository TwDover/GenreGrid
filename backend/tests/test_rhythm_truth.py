# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Roadmap v3 item 10.3 — the rhythm scorer measures what the band played.

`rhythm` was the search's bottleneck: it sat red for whole styles no matter how
many times the dice were re-rolled (trap_soul 0.498 across all 16 seeds, rock
0.800, hyperpop 0.736), because in three separate places the scorer compared the
music against something the generators were never going to play.

  1. **The barline.** Steps were binned by truncating to a bar and rounding
     inside it, so a note a hair *before* a barline rounded to step 16 and was
     dropped. Humanize, swing and groove_push routinely place the downbeat
     5–20ms early — a rock kit playing beats 1 and 3 scored as playing only 3,
     and a jazz kit's downbeat kick disappeared altogether.
  2. **The comp grid.** `chord_rhythm` is one bar, but the generator reads it
     per chord *window* and guarantees a hit at each window's start (otherwise a
     pad-hold pattern drops half the progression at two chords per bar). The
     reference didn't, so a correct comp scored 0.00 — no shared non-zero step.
  3. **The groove overlay.** 13 styles have their drum fields replaced by a
     mined groove before a note is generated; the scoring style was built from
     the style JSON and never saw it.
"""
import pytest

from app.core.meter import Meter, DEFAULT_METER
from app.core.constants import DRUM_CHANNEL
from app.services.midi_writer import NoteEvent
from app.services.quality import (
    _KICK_PITCH, _comp_reference, _comp_windows, _extract_steps, _rhythm_fit,
)

M44, M34 = DEFAULT_METER, Meter(3, 4)
PAD_HOLD = [1] + [0] * 15


def _kick(beat):
    return NoteEvent(_KICK_PITCH, beat, 0.25, 100, DRUM_CHANNEL)


def _chord(beat):
    return NoteEvent(60, beat, 0.5, 90, 0)


def _steps(events, bars=4, meter=M44):
    return _extract_steps(events, _KICK_PITCH, bars, DRUM_CHANNEL, meter)


# ── 1. the barline ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("nudge", [-0.02, -0.005, -0.09, 0.0, 0.02])
def test_a_downbeat_played_early_is_still_a_downbeat(nudge):
    """The single fix with the widest reach: every humanized kit pushes the
    downbeat a few milliseconds early, and every one of those notes used to
    vanish from the scorer's view."""
    vec = _steps([_kick(4.0 + nudge)])
    assert vec[0] == 1.0, vec
    assert sum(vec) == 1.0


def test_a_laid_back_sixteenth_is_not_pulled_onto_the_downbeat():
    """The rounding has to stay honest in the other direction: 3.75 is its own
    step, not an early bar 2."""
    vec = _steps([_kick(3.75)])
    assert vec[15] == 1.0


def test_the_rock_signature_reads_as_beats_one_and_three():
    """The shape that was scoring 0.61 against its own kick pattern."""
    kicks = []
    for bar in range(4):
        kicks.append(_kick(bar * 4 - 0.007 if bar else 0.0))   # downbeat, pushed
        kicks.append(_kick(bar * 4 + 2.016))                   # beat 3, laid back
    vec = _steps(kicks)
    assert vec[0] == pytest.approx(0.5)
    assert vec[8] == pytest.approx(0.5)


def test_notes_past_the_last_bar_are_still_excluded():
    assert sum(_steps([_kick(15.8)], bars=4)) == 1.0     # last step of bar 4
    assert sum(_steps([_kick(16.0)], bars=4)) == 0.0
    # A note pushed early against the *end* of the generation quantises into a
    # bar that doesn't exist, and is dropped — the same rule, applied honestly.
    assert sum(_steps([_kick(15.99)], bars=4)) == 0.0


def test_the_barline_rounds_on_this_meters_bar():
    """In 3/4 the barline is beat 3, not beat 4."""
    vec = _steps([_kick(2.99)], bars=4, meter=M34)
    assert len(vec) == 12
    assert vec[0] == 1.0


# ── 2. the comp grid ──────────────────────────────────────────────────────────

def test_one_chord_per_bar_leaves_the_pattern_alone():
    assert _comp_windows(PAD_HOLD, 16, 1) == [float(v) for v in PAD_HOLD]


def test_two_chords_per_bar_expects_a_hit_on_the_second_chord():
    ref = _comp_windows(PAD_HOLD, 16, 2)
    assert ref[0] == 1.0 and ref[8] == 1.0
    assert sum(ref) == 2.0


def test_a_window_that_already_comps_is_not_given_an_extra_hit():
    """The generator only forces a hit when the window would be silent."""
    busy = [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0]
    assert _comp_windows(busy, 16, 2) == [float(v) for v in busy]


def test_the_comp_reference_mixes_the_sections_by_bar_count():
    """A chorus comps twice as fast as the verse around it, and the generated
    vector averages both — so the reference has to as well."""
    sections = [{"bars": 12, "chords_per_bar": 1}, {"bars": 4, "chords_per_bar": 2}]
    ref = _comp_reference(PAD_HOLD, 16, sections)
    assert ref[0] == pytest.approx(1.0)
    assert ref[8] == pytest.approx(0.25)      # 4 of 16 bars comped twice a bar


def test_the_comp_reference_without_sections_is_the_plain_pattern():
    assert _comp_reference(PAD_HOLD, 16, None) == [float(v) for v in PAD_HOLD]


def test_a_correct_two_chord_comp_is_scored_on_its_own_grid():
    """The trap_soul case: pad_hold at two chords per bar, played exactly as the
    generator plays it. In production the two bugs compounded — the downbeat
    comp was pushed early and dropped, leaving only the beat-3 window against a
    reference that expected only the downbeat, which is how a correct comp
    scored a flat 0.00."""
    style = {"chord_rhythm": PAD_HOLD, "drums": {}}
    chords = [_chord(bar * 4 + off) for bar in range(4) for off in (-0.01, 2.0)]
    sections = [{"bars": 4, "chords_per_bar": 2}]

    on_the_bar_grid, _ = _rhythm_fit([], chords, style, 4, M44, None)
    on_the_comp_grid, _ = _rhythm_fit([], chords, style, 4, M44, sections)
    assert on_the_comp_grid > 0.99
    assert on_the_bar_grid < 0.75


# ── 3. the groove overlay ─────────────────────────────────────────────────────

def test_the_scorer_judges_the_mined_groove_the_drummer_played(monkeypatch):
    """13 styles play a mined groove instead of their authored drum fields. The
    scoring style has to be overlaid too, or the kit is measured against a
    pattern that was replaced before a note existed."""
    import app.services.quality as quality_mod
    from app.models.schemas import GenerateRequest
    from app.services.generation import _run_attempt, _overlay_groove
    from app.services.style_loader import load_style

    seen = {}
    original = quality_mod.score_generation

    def _spy(events, style, *args, **kwargs):
        seen["kick"] = style.get("drums", {}).get("kick_pattern")
        return original(events, style, *args, **kwargs)

    monkeypatch.setattr("app.services.generation.score_generation", _spy)

    style = {**load_style("rock"), "_humanize_scale": 0.5}
    mined = _overlay_groove(style, True)["drums"]["kick_pattern"]
    assert mined != style["drums"]["kick_pattern"], "rock has no mined groove to test"

    req = GenerateRequest(style_id="rock", key="C", scale="major", bpm=120, bars=8,
                          complexity=0.5, variation=0.4, mode="arrangement",
                          parts=["chords", "bass", "melody", "drums"])
    # scoring_style is what production passes (library-blended, style-JSON based)
    _run_attempt(req, style, 2026, False, 0.0, False, False, scoring_style=dict(style))
    assert seen["kick"] == mined


def test_a_style_without_a_mined_groove_scores_against_its_own_pattern():
    from app.services.generation import _overlay_groove
    from app.services.style_loader import load_style

    style = load_style("trap_soul")
    assert _overlay_groove(style, True)["drums"] == style["drums"]
