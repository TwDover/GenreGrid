# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Roadmap v3 item 11.4 — the search repairs what the scorer flagged.

The quality search re-rolled the whole attempt up to five times even when one
dimension was a hair short. `plan_repair` turns a single red dimension into the
cheapest edit that addresses it, and `run_quality_search` — now the one
implementation all four callers share — decides whether that edit was an
improvement.

Pinned here:
  * a repair is proposed only when exactly one gated dimension is red AND it is
    close enough to green to be worth a run (both thresholds are measured, see
    repair.py);
  * the search prefers a GREEN attempt over a higher-scoring red one, and the
    events it returns are always the ones it scored;
  * evaluating a seed does not depend on remaining budget — the property that
    lets a replay re-derive a build's repairs from the winning seed alone.
"""
import pytest

from app.services.generation import (
    _GREEN_THRESHOLD, _QUALITY_DIMS, evaluate_seed, run_quality_search,
)
from app.services.midi_writer import NoteEvent
from app.services.repair import plan_repair

DIMS = _QUALITY_DIMS
T = _GREEN_THRESHOLD


def _q(flags=None, total=0.9, **red):
    q = {d: 0.90 for d in DIMS}
    q.update(red)
    q["total"] = total
    q["flags"] = list(flags or [])
    return q


def _notes(n, velocity=80):
    return [NoteEvent(60, i * 0.5, 0.5, velocity, 0) for i in range(n)]


def _events(melody=80, chords=80, bass=80):
    return {"melody": _notes(8, melody), "chords": _notes(8, chords),
            "bass": _notes(8, bass), "drums": _notes(8)}


def _plan(quality, events=None, salt=1):
    return plan_repair(quality, events if events is not None else _events(), DIMS, T, salt)


# ── when a repair is proposed at all ──────────────────────────────────────────

def test_no_repair_when_nothing_is_red():
    assert _plan(_q()) is None


def test_no_repair_when_two_dimensions_are_red():
    """Two red dimensions mean the attempt is broadly wrong, not that one part
    misbehaved — a full re-roll is the honest response."""
    assert _plan(_q(density=0.79, mix=0.78,
                    flags=["Melody is much sparser than expected for this style"])) is None


def test_no_repair_when_the_dimension_is_far_below_green():
    """Measured: of 165 repairs attempted on wider gaps, exactly zero converted."""
    assert _plan(_q(density=0.50,
                    flags=["Melody is much sparser than expected for this style"])) is None


def test_no_repair_without_a_quality_score():
    assert _plan(None) is None


@pytest.mark.parametrize("dim", ["harmonic", "rhythm", "separation"])
def test_dimensions_with_no_cheap_repair_fall_back_to_a_full_reroll(dim):
    """`harmonic` is shared by every part; `rhythm` and `separation` were
    measured at 3% and 8% conversion — worse than the re-roll they'd replace."""
    assert _plan(_q(**{dim: T - 0.01})) is None


# ── density: re-roll the part the flag names ──────────────────────────────────

@pytest.mark.parametrize("flag,part", [
    ("Melody is much sparser than expected for this style", "melody"),
    ("Melody is much denser than expected for this style",  "melody"),
    ("Bass is much sparser than expected",                  "bass"),
    ("Bass is much denser than expected",                   "bass"),
])
def test_density_rerolls_the_flagged_part(flag, part):
    repair = _plan(_q(density=T - 0.02, flags=[flag]), salt=3)
    assert repair is not None
    assert (repair.kind, repair.part) == ("reroll", part)
    assert repair.kwargs == {"part_salts": {part: 3}}


def test_density_without_a_naming_flag_has_no_target():
    assert _plan(_q(density=T - 0.02, flags=["Something else entirely"])) is None


def test_a_part_that_isnt_playing_cannot_be_repaired():
    events = _events()
    events["bass"] = []
    assert _plan(_q(density=T - 0.02, flags=["Bass is much sparser than expected"]),
                 events) is None


# ── mix: rescale, don't regenerate ────────────────────────────────────────────

def test_a_buried_melody_is_lifted_not_regenerated():
    repair = _plan(_q(mix=T - 0.03), _events(melody=20, chords=90))
    assert repair is not None
    assert repair.kind == "velocity"
    assert repair.part == "melody"
    assert repair.kwargs["velocity_trim"]["melody"] > 1.0


def test_a_dominant_melody_is_brought_down():
    repair = _plan(_q(mix=T - 0.03), _events(melody=120, chords=40))
    assert repair.part == "melody"
    assert repair.kwargs["velocity_trim"]["melody"] < 1.0


def test_the_bass_is_repaired_by_moving_the_bass():
    """Both mix ratios are measured against the chords, so trimming the chords
    would fix one by breaking the other."""
    repair = _plan(_q(mix=T - 0.03), _events(melody=60, chords=100, bass=30))
    assert repair.part == "bass"
    assert repair.kwargs["velocity_trim"]["bass"] > 1.0


def test_the_weaker_of_the_two_mix_terms_is_the_one_repaired():
    """A melody ratio sitting just inside its green band must not shadow a bass
    that is genuinely buried."""
    events = _events(melody=44, chords=100, bass=20)   # melody ratio 0.44 (green), bass 0.20
    assert _plan(_q(mix=T - 0.05), events).part == "bass"


def test_a_repair_may_not_rewrite_the_arrangements_dynamics():
    repair = _plan(_q(mix=T - 0.03), _events(melody=1, chords=127))
    assert 0.55 <= repair.kwargs["velocity_trim"]["melody"] <= 1.80


def test_no_mix_repair_when_the_balance_is_already_right():
    """`mix` can be red for a reason velocity scaling can't reach; inventing a
    trim anyway would just move the problem."""
    assert _plan(_q(mix=T - 0.03), _events(melody=60, chords=100, bass=110)) is None


# ── the search ────────────────────────────────────────────────────────────────

def _runner(script):
    """Fake `run`: `script` maps call index → quality dict (or None)."""
    calls = []

    def run(seed, **kwargs):
        quality = script[len(calls)]
        calls.append((seed, kwargs))
        return (_events(), {}, {}, [], quality, {}, [])

    run.calls = calls
    return run


def test_a_green_attempt_beats_a_higher_scoring_red_one():
    """The old loop compared attempts on `total` alone but broke out of the loop
    on green — so a green attempt with a lower total was reported by seed while
    the events returned were the red attempt's."""
    run = _runner({0: _q(rhythm=0.60, total=0.95), 1: _q(total=0.83)})
    found = run_quality_search(run, 4242)
    assert found.green
    assert found.result[4] is found.quality      # events and score come from one attempt
    assert found.quality["total"] == 0.83


def test_the_search_stops_at_the_first_green_attempt():
    run = _runner({0: _q(total=0.9)})
    found = run_quality_search(run, 7)
    assert found.runs == 1 and found.seed == 7


def test_a_repair_that_helps_is_kept():
    run = _runner({0: _q(density=T - 0.02, total=0.80,
                         flags=["Bass is much sparser than expected"]),
                   1: _q(total=0.88)})
    found = evaluate_seed(run, 99)
    assert found.green and found.runs == 2
    assert run.calls[1][1] == {"part_salts": {"bass": 1}}
    assert [r.dimension for r in found.repairs] == ["density"]


def test_a_repair_that_makes_things_worse_is_discarded():
    before = _q(density=T - 0.02, total=0.80,
                flags=["Bass is much sparser than expected"])
    run = _runner({0: before, 1: _q(density=0.40, harmonic=0.30, total=0.55)})
    found = evaluate_seed(run, 99)
    assert found.quality is before
    assert found.result[4] is before
    assert found.repairs == ()


def test_a_green_attempt_is_never_repaired():
    run = _runner({0: _q(total=0.9)})
    assert evaluate_seed(run, 5).runs == 1


def test_evaluating_a_seed_does_not_depend_on_the_budget():
    """A section's identity has to be reproducible from its seed alone —
    `fixed_section_seeds` carries nothing else — so the repair a seed gets can't
    depend on how much search budget happened to be left when it ran."""
    script = {0: _q(density=T - 0.02, total=0.80,
                    flags=["Melody is much denser than expected for this style"]),
              1: _q(total=0.88)}
    first = evaluate_seed(_runner(script), 31337)
    replay = evaluate_seed(_runner(script), 31337)
    assert first.quality == replay.quality
    assert [r.describe() for r in first.repairs] == [r.describe() for r in replay.repairs]


def test_the_search_survives_an_attempt_that_cannot_be_scored():
    run = _runner({0: None, 1: _q(total=0.9)})
    found = run_quality_search(run, 11)
    assert found.green


# ── the replay contract ───────────────────────────────────────────────────────

def _repaired_song(monkeypatch, repair_part, **replay_kwargs):
    """Build a song whose sections all keep a repair on `repair_part`, then replay
    it from the recorded seeds. Returns (built_events, replayed_events).

    Forcing the repair (and its acceptance) keeps the test about the replay
    contract instead of about whether a natural repair happened to fire and win
    for this particular seed.
    """
    from app.models.schemas import BuildSongRequest
    from app.services.song_builder import _generate_song_sections
    from app.services.style_loader import load_style
    import app.services.generation as gen
    from app.services.repair import Repair

    monkeypatch.setattr(
        gen, "plan_repair",
        lambda q, e, dims, threshold, salt=1: Repair(
            "density", "reroll", repair_part, {"part_salts": {repair_part: salt}}),
    )
    monkeypatch.setattr(gen, "_better", lambda candidate, incumbent: True)

    parts = ["chords", "bass", "melody", "drums"]
    req = BuildSongRequest(style_id="lofi", key="C", scale="major", bpm=90,
                           template="compact", parts=parts, seed=7)
    style = {**load_style("lofi"), "_humanize_scale": 0.5}
    args = (req, style, 90, 7, 0, False, False, style.get("groove_push", 0.0))

    built, _s, _b, seeds, _p = _generate_song_sections(*args)
    replayed, _s, _b, _s2, _p = _generate_song_sections(
        *args, fixed_section_seeds=seeds, **replay_kwargs)
    return built, replayed


def _notes_of(events, part):
    return [(round(e.start, 4), e.pitch, e.velocity) for e in events[part]]


def test_replaying_a_song_reproduces_its_repairs(monkeypatch):
    """`section_seeds` carries only the seed, so a replay has to re-derive each
    section's repair — otherwise every repaired section comes back unrepaired."""
    built, replayed = _repaired_song(monkeypatch, "chords")
    for part in ("chords", "bass", "melody", "drums"):
        assert _notes_of(replayed, part) == _notes_of(built, part), f"{part} drifted"


def test_regenerating_a_stem_keeps_the_other_parts_repairs(monkeypatch):
    """The repair is derived from the UNregenerated attempt, so which repair
    fires can't depend on the stem the user is re-rolling. Chords are repaired
    here and the bass is the stem — nothing the comp reads changes with it."""
    built, replayed = _repaired_song(monkeypatch, "chords",
                                     regen_part="bass", regen_salt=99)
    assert _notes_of(replayed, "bass") != _notes_of(built, "bass"), "the stem was not re-rolled"
    assert _notes_of(replayed, "chords") == _notes_of(built, "chords")
